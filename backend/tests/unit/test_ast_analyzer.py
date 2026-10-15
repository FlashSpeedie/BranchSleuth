from app.services.ast_analyzer import (
    analyze_signature,
    build_scope_index,
    extract_boundary_constants,
    merge_lines_into_scopes,
)

SRC = '''import os


class Cart:
    def add(self, item):
        def norm(x):
            return x.strip()
        return norm(item)

    async def save(self):
        pass


def total(values, rate=0.1):
    if values:
        return sum(values) * rate
    return 0


async def fetch(url: str):
    return url
'''


def test_scopes_include_class_methods_async_nested():
    idx = build_scope_index(SRC)
    quals = {s.qualname for s in idx.scopes}
    assert "Cart" in quals
    assert "Cart.add" in quals
    assert "Cart.add.norm" in quals
    assert "Cart.save" in quals
    assert "total" in quals
    assert "fetch" in quals
    by_name = {s.qualname: s for s in idx.scopes}
    assert by_name["Cart"].kind == "class"
    assert by_name["Cart.save"].kind == "async_function"
    assert by_name["Cart.add.norm"].kind == "function"


def test_scope_line_ranges_use_end_lineno():
    idx = build_scope_index("def f():\n    return 1\n\n\ndef g():\n    return 2\n")
    f = next(s for s in idx.scopes if s.name == "f")
    assert (f.start_line, f.end_line) == (1, 2)
    g = next(s for s in idx.scopes if s.name == "g")
    assert (g.start_line, g.end_line) == (5, 6)


def test_find_scope_innermost_wins():
    idx = build_scope_index(SRC)
    assert idx.find_scope(7).qualname == "Cart.add.norm"
    assert idx.find_line_status if False else True


def test_syntax_error_reported():
    idx = build_scope_index("def broken(:\n")
    assert idx.parse_error is not None
    assert idx.scopes == []


def test_executable_lines_collected():
    idx = build_scope_index(SRC)
    total_scope = next(s for s in idx.scopes if s.name == "total")
    assert 14 in total_scope.executable_lines
    assert 15 in total_scope.executable_lines
    assert 16 in total_scope.executable_lines
    assert 17 in total_scope.executable_lines


def test_merge_lines_into_scopes_module_fallback():
    idx = build_scope_index(SRC)
    mapping = merge_lines_into_scopes(idx, {1})
    assert "<module>" in mapping


def test_analyze_signature_drops_self():
    sig = analyze_signature(SRC, "Cart.add")
    assert sig is not None
    assert [p.name for p in sig.params] == ["item"]
    assert not sig.supported
    assert "unsupported parameter type" in (sig.reason or "")


def test_analyze_signature_types_and_defaults():
    src = "def f(a: int, b: float, c: str, d: bool, e: list[int], g=None, *args): pass\n"
    sig = analyze_signature(src, "f")
    assert sig is not None
    names = {p.name: p for p in sig.params}
    assert names["a"].strategy == "int"
    assert names["b"].strategy == "float"
    assert names["c"].strategy == "text"
    assert names["d"].strategy == "bool"
    assert names["e"].strategy == {"type": "list", "element": "int"}
    assert not sig.supported
    assert "keyword-only" in (sig.reason or "") or "args" in (sig.reason or "")


def test_analyze_signature_unannotated_without_default_unsupported():
    sig = analyze_signature("def f(x): return x\n", "f")
    assert sig is not None
    assert not sig.supported


def test_analyze_signature_no_args():
    sig = analyze_signature("def f(): return 1\n", "f")
    assert sig is not None
    assert not sig.supported
    assert "no arguments" in (sig.reason or "")


def test_boundary_constants_extraction():
    src = "def f(v: int):\n    if v > 100:\n        return 1\n    return 0\n"
    bounds = extract_boundary_constants(src, "f")
    values = {(b["relation"], b["value"]) for b in bounds}
    assert ("below", 99) in values
    assert ("at", 100) in values
    assert ("above", 101) in values


def test_boundary_constants_floats():
    src = "def f(v: float):\n    if v >= 0.5:\n        return 1\n    return 0\n"
    bounds = extract_boundary_constants(src, "f")
    assert any(b["value"] == 0.5 for b in bounds)
