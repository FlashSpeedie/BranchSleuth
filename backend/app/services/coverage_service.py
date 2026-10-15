from __future__ import annotations

from dataclasses import dataclass, field

from coverage import CoverageData


@dataclass
class ContextLines:
    context: str
    lines: set[int]


@dataclass
class CoverageFacts:
    measured_files: list[str] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)
    file_context_lines: dict[str, list[ContextLines]] = field(default_factory=dict)
    error: str | None = None


def load_coverage(cov_path: str) -> CoverageFacts:
    facts = CoverageFacts()
    from pathlib import Path

    if not Path(cov_path).exists():
        facts.error = "coverage data file not present"
        return facts
    try:
        data = CoverageData(basename=cov_path)
        data.read()
    except Exception as e:
        facts.error = f"coverage data unreadable: {type(e).__name__}"
        return facts
    try:
        facts.contexts = [c for c in data.measured_contexts() if c]
        facts.measured_files = list(data.measured_files())
        for f in facts.measured_files:
            by_lineno = data.contexts_by_lineno(f) or {}
            per_ctx: dict[str, set[int]] = {}
            for lineno, ctx_list in by_lineno.items():
                for ctx in ctx_list:
                    per_ctx.setdefault(ctx, set()).add(lineno)
            facts.file_context_lines[f] = [
                ContextLines(context=ctx, lines=lines)
                for ctx, lines in per_ctx.items()
                if ctx
            ]
    except Exception as e:
        facts.error = f"coverage data parsing failed: {type(e).__name__}"
        return facts
    return facts


def match_test(context_name: str, node_id: str, test_name: str) -> bool:
    ctx = context_name.split("|", 1)[0] if "|" in context_name else context_name
    if not ctx:
        return False
    if ctx == node_id or ctx == test_name:
        return True
    if ctx.endswith(node_id) or node_id.endswith(ctx):
        return True
    if "::" in ctx and ctx.rsplit("::", 1)[-1] == test_name:
        return True
    return False
