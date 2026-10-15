import json

import pytest

from app.db.models import AnalysisRun, Repository, RunStatus
from app.engine.pipeline import execute_analysis
from tests.conftest import ensure_workspace
from tests.fixture_builder import build_fixture_git_repo

PROPERTY_CODE = """import math

def check(kwargs, outcome):
    subtotal = kwargs["subtotal"]
    if outcome["kind"] != "return":
        return False
    value = outcome["value"]
    if subtotal <= 100:
        return value == subtotal
    return math.isclose(value, subtotal * 0.9, rel_tol=1e-9)
"""

pytestmark = pytest.mark.docker


def docker_available() -> bool:
    try:
        from app.worker_runtime.docker_worker import get_docker_client

        client = get_docker_client()
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def docker_client_module():
    if not docker_available():
        pytest.skip("Docker daemon not available; runtime verification cannot be executed")
    from app.worker_runtime.docker_worker import ensure_worker_image, get_docker_client

    client = get_docker_client()
    ensure_worker_image(client)
    yield client
    client.close()


def test_end_to_end_regression_reproduction(sqlite_db, tmp_path, data_dir, docker_client_module):
    repo_path, modified_sha = build_fixture_git_repo(tmp_path / "tinyshop-repo")
    with sqlite_db() as db:
        repo = Repository(name="tinyshop", source_type="local", local_path=repo_path, workspace_id=ensure_workspace(db).id)
        db.add(repo)
        db.commit()
        run = AnalysisRun(
            repository_id=repo.id,
            baseline_ref=f"{modified_sha}~1",
            target_ref=modified_sha,
            options={
                "property_code": PROPERTY_CODE,
                "property_target": "tinyshop/pricing.py::apply_discount",
                "hypothesis_max_examples": 60,
                "hypothesis_deadline_ms": 2000,
            },
        )
        db.add(run)
        db.commit()
        run_id = run.id

    execute_analysis(run_id, sqlite_db)

    with sqlite_db() as db:
        run = db.get(AnalysisRun, run_id)
        assert run.status == RunStatus.COMPLETED.value, f"error: {run.error_message}"
        assert run.resolved_target_sha == modified_sha
        summary = run.summary
        assert summary["runtime_status"] == "executed", summary.get("runtime_note")

        from app.db.models import ChangedFile, ChangedScope, TestRecord, VerificationAttempt

        f = db.query(ChangedFile).filter(ChangedFile.run_id == run_id).one()
        assert f.path == "tinyshop/pricing.py"
        scope = db.query(ChangedScope).filter(ChangedScope.run_id == run_id).one()
        assert scope.qualname == "apply_discount"
        assert scope.changed_lines == [6]
        assert scope.coverage_status == "CHANGED_AND_EXECUTED"
        assert scope.covered_changed_lines == [6]
        assert scope.uncovered_changed_lines == []

        tests = db.query(TestRecord).filter(TestRecord.run_id == run_id).all()
        assert len(tests) == 3
        assert all(t.category == "STABLE_PASS" for t in tests)
        assert all(t.baseline_outcome == "passed" and t.modified_outcome == "passed" for t in tests)
        exercising = [t for t in tests if t.executed_changed_lines]
        assert exercising, "per-test coverage should attribute the changed line to at least one test"
        assert any(
            "tinyshop/pricing.py" in t.executed_changed_lines and 6 in t.executed_changed_lines["tinyshop/pricing.py"]
            for t in exercising
        )

        attempt = db.query(VerificationAttempt).filter(VerificationAttempt.run_id == run_id).one()
        assert attempt.classification == "PROVEN_FAILURE", (attempt.classification, attempt.rationale)
        assert attempt.function_qualname == "apply_discount"
        assert attempt.input_payload == {"subtotal": "100"}
        assert attempt.reproducible is True
        assert attempt.minimized is False
        assert attempt.detail.get("via") == "boundary"
        assert attempt.modified_outcome["repr"] == "90.0"
        assert attempt.baseline_outcome["repr"] == "100"
        assert attempt.environment["network"] == "disabled"
        assert attempt.environment["python_version"].startswith("3.12")

        assert summary["proven_failures"] == 1
        assert summary["tests"]["categories"]["STABLE_PASS"] == 3
        assert summary["tests"]["baseline_outcome"] == "ok"
        assert summary["tests"]["modified_outcome"] == "ok"


def test_report_and_graph_evidence(sqlite_db, tmp_path, data_dir, docker_client_module):
    from app.services.report_service import build_report_json, build_report_markdown

    repo_path, modified_sha = build_fixture_git_repo(tmp_path / "tinyshop-repo2")
    with sqlite_db() as db:
        repo = Repository(name="tinyshop", source_type="local", local_path=repo_path, workspace_id=ensure_workspace(db).id)
        db.add(repo)
        db.commit()
        run = AnalysisRun(
            repository_id=repo.id,
            baseline_ref=f"{modified_sha}~1",
            target_ref=modified_sha,
            options={
                "property_code": PROPERTY_CODE,
                "property_target": "tinyshop/pricing.py::apply_discount",
            },
        )
        db.add(run)
        db.commit()
        run_id = run.id

    execute_analysis(run_id, sqlite_db)

    with sqlite_db() as db:
        run = db.get(AnalysisRun, run_id)
        repo = db.get(Repository, run.repository_id)
        report = build_report_json(db, run, repo)
        assert report["analysis"]["resolved_target"] == modified_sha
        assert report["analysis"]["summary"]["proven_failures"] == 1
        verifications = report["verifications"]
        assert any(v["classification"] == "PROVEN_FAILURE" and v["input"] == {"subtotal": "100"} for v in verifications)
        assert any(v["category"] == "STABLE_PASS" for v in report["tests"])
        assert "-    if subtotal > 100:" in report["unified_diff"]
        assert "+    if subtotal >= 100:" in report["unified_diff"]
        dump = json.dumps(report)
        assert "postgres://" not in dump
        assert "npg_" not in dump
        markdown = build_report_markdown(db, run, repo)
        assert "PROVEN_FAILURE" in markdown
        assert '"subtotal": "100"' in markdown
        assert "not executed" in markdown.lower() or "runtime verification" in markdown.lower()
