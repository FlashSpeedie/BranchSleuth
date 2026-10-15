from __future__ import annotations

import ast
from dataclasses import dataclass, field

SCOPE_KINDS = {"FunctionDef": "function", "AsyncFunctionDef": "async_function", "ClassDef": "class"}


@dataclass
class Scope:
    kind: str
    name: str
    qualname: str
    start_line: int
    end_line: int
    executable_lines: set[int] = field(default_factory=set)


@dataclass
class ScopeIndex:
    scopes: list[Scope] = field(default_factory=list)
    parse_error: str | None = None

    def find_scope(self, line: int) -> Scope | None:
        best: Scope | None = None
        for s in self.scopes:
            if s.start_line <= line <= s.end_line:
                if best is None or (s.end_line - s.start_line) < (best.end_line - best.start_line):
                    best = s
        return best


def _executable_lines(node: ast.AST) -> set[int]:
    lines: set[int] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.stmt):
            lineno = getattr(n, "lineno", None)
            if isinstance(lineno, int):
                lines.add(lineno)
    return lines


def build_scope_index(source: str) -> ScopeIndex:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ScopeIndex(parse_error=f"line {e.lineno}: {e.msg}" if e.lineno else str(e))

    scopes: list[Scope] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            kind = SCOPE_KINDS.get(type(child).__name__)
            name = getattr(child, "name", None)
            if kind and name:
                start = int(getattr(child, "lineno", 0))
                qualname = f"{prefix}.{name}" if prefix else name
                end = int(getattr(child, "end_lineno", 0) or start)
                scopes.append(
                    Scope(
                        kind=kind,
                        name=name,
                        qualname=qualname,
                        start_line=start,
                        end_line=end,
                        executable_lines=_executable_lines(child),
                    )
                )
                visit(child, qualname)
            else:
                visit(child, prefix)

    visit(tree, "")
    scopes.sort(key=lambda s: (s.start_line, -(s.end_line - s.start_line)))
    return ScopeIndex(scopes=scopes)


def merge_lines_into_scopes(index: ScopeIndex, lines: set[int]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for line in sorted(lines):
        scope = index.find_scope(line)
        key = scope.qualname if scope else "<module>"
        out.setdefault(key, []).append(line)
    return out


def resolve_qualname_source(source: str, qualname: str) -> ast.AST | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    parts = qualname.split(".")
    node: ast.AST = tree
    for part in parts:
        found = None
        for child in ast.iter_child_nodes(node):
            if getattr(child, "name", None) == part and isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                found = child
                break
        if found is None:
            return None
        node = found
    return node


@dataclass
class ParamSpec:
    name: str
    kind: str = "unsupported"
    default: object = None
    has_default: bool = False
    strategy: dict | str | None = None


@dataclass
class FunctionSignature:
    qualname: str
    params: list[ParamSpec] = field(default_factory=list)
    supported: bool = True
    reason: str | None = None


_SUPPORTED_BUILTINS = {"int": "int", "float": "float", "bool": "bool", "str": "text"}


def _annotation_to_strategy(ann: ast.expr | None) -> dict | str | None:
    if ann is None:
        return None
    try:
        name = None
        origin = None
        args: list[ast.expr] = []
        if isinstance(ann, ast.Name):
            name = ann.id
        elif isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            name = ann.value
        elif isinstance(ann, ast.Attribute):
            name = ann.attr
        elif isinstance(ann, ast.Subscript):
            base = ann.value
            name = getattr(base, "id", None) or getattr(base, "attr", None)
            origin = name
            sl = ann.slice
            elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            args = [e for e in elts if isinstance(e, ast.expr)]
        if origin in ("List", "list", "Sequence", "tuple"):
            inner = args[0] if args else None
            child = _annotation_to_strategy(inner)
            if child is None and inner is not None:
                return None
            return {"type": "list", "element": child}
        if origin in ("Optional", "Union") or (name == "Union"):
            variants = []
            for a in args:
                s = _annotation_to_strategy(a)
                if s is None and a is not None:
                    return None
                if s is not None:
                    variants.append(s)
            return {"type": "union", "variants": variants}
        if origin in ("Dict", "dict", "Mapping"):
            return None
        if name in _SUPPORTED_BUILTINS:
            return _SUPPORTED_BUILTINS[name]
        return None
    except Exception:
        return None


def analyze_signature(source: str, qualname: str) -> FunctionSignature | None:
    node = resolve_qualname_source(source, qualname)
    if node is None or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    sig = FunctionSignature(qualname=qualname)
    if isinstance(node, ast.AsyncFunctionDef):
        sig.supported = False
        sig.reason = "async functions are not supported for targeted invocation yet"
        return sig
    args = node.args
    all_args = list(args.posonlyargs) + list(args.args)
    if all_args and all_args[0].arg in ("self", "cls") and "." in qualname:
        all_args = all_args[1:]
    defaults_offset = len(all_args) - len(args.defaults) if all_args else 0
    defaults_offset = max(defaults_offset, 0)
    for i, a in enumerate(all_args):
        spec = ParamSpec(name=a.arg)
        strategy = _annotation_to_strategy(a.annotation)
        if strategy is None:
            spec.kind = "unsupported"
        else:
            spec.kind = "arg"
            spec.strategy = strategy
        if i >= defaults_offset:
            spec.has_default = True
            try:
                spec.default = ast.literal_eval(args.defaults[i - defaults_offset])
            except Exception:
                spec.has_default = False
        sig.params.append(spec)
    if args.vararg or args.kwarg or args.kwonlyargs:
        sig.supported = False
        sig.reason = "*args/**kwargs/keyword-only parameters are not supported yet"
    if any(p.kind == "unsupported" and not p.has_default for p in sig.params):
        sig.supported = False
        sig.reason = "unsupported parameter type annotations"
    if not sig.params:
        sig.supported = False
        sig.reason = "function takes no arguments (nothing to vary)"
    return sig


def extract_boundary_constants(source: str, qualname: str) -> list[dict]:
    node = resolve_qualname_source(source, qualname)
    if node is None:
        return []
    out: list[dict] = []
    seen: set[tuple[str, float | int]] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Compare):
            if not any(isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE)) for op in n.ops):
                continue
            for comparator in n.comparators:
                try:
                    val = ast.literal_eval(comparator)
                except Exception:
                    continue
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    continue
                for key in ("below", "at", "above"):
                    cand = val - 1 if key == "below" else (val if key == "at" else val + 1)
                    if abs(cand) > 10**12:
                        continue
                    k = (key, cand)
                    if k not in seen:
                        seen.add(k)
                        out.append({"relation": key, "to": val, "value": cand})
    return out[:60]
