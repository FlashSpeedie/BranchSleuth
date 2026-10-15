import sys
from pathlib import Path

from coverage import Coverage

from app.services.coverage_service import load_coverage, match_test

SRC = '''def add(a, b):
    return a + b


def mul(a, b):
    return a * b
'''


def _make_cov_file(tmp_path: Path, contexts: dict[str, list[int]]) -> str:
    src_path = tmp_path / "calcs.py"
    src_path.write_text(SRC)
    data_file = str(tmp_path / ".coverage")
    cov = Coverage(data_file=data_file, include=[f"{src_path}"])
    cov.start()
    try:
        sys.path.insert(0, str(tmp_path))
        for ctx, lines in contexts.items():
            cov.switch_context(ctx)
            if "import" in lines:
                import calcs  # noqa: F401
            if "add" in lines:
                calcs.add(1, 2)
            if "mul" in lines:
                calcs.mul(2, 3)
    finally:
        cov.stop()
        cov.save()
    return data_file


def test_load_coverage_contexts_and_lines(tmp_path):
    data_file = _make_cov_file(tmp_path, {"test_add": ["import", "add"], "test_mul": ["import", "mul"]})
    facts = load_coverage(data_file)
    assert facts.error is None
    assert set(facts.contexts) >= {"test_add", "test_mul"}
    src_key = [f for f in facts.measured_files if f.replace("\\", "/").endswith("calcs.py")]
    assert src_key, f"measured files: {facts.measured_files}"
    per_ctx = facts.file_context_lines[src_key[0]]
    by_ctx = {c.context: c.lines for c in per_ctx}
    assert 2 in by_ctx["test_add"]
    assert 6 not in by_ctx["test_add"]
    assert 6 in by_ctx["test_mul"]
    assert 2 not in by_ctx["test_mul"]


def test_load_coverage_missing_file(tmp_path):
    facts = load_coverage(str(tmp_path / "missing.coverage"))
    assert facts.error is not None


def test_match_test_variants():
    assert match_test("tests/test_x.py::test_a", "tests/test_x.py::test_a", "test_a")
    assert match_test("test_a", "tests/test_x.py::test_a", "test_a")
    assert match_test("tests/test_x.py::test_a", "test_a", "test_a")
    assert not match_test("", "tests/test_x.py::test_a", "test_a")
    assert not match_test("test_other", "tests/test_x.py::test_a", "test_a")
