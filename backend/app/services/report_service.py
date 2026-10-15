from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AnalysisRun, ChangedFile, JobEvent, Repository, TestRecord, VerificationAttempt, utcnow


def build_report_json(db: Session, run: AnalysisRun, repo: Repository) -> dict:
    files = db.query(ChangedFile).filter(ChangedFile.run_id == run.id).order_by(ChangedFile.path).all()
    tests = db.query(TestRecord).filter(TestRecord.run_id == run.id).order_by(TestRecord.node_id).all()
    attempts = db.query(VerificationAttempt).filter(VerificationAttempt.run_id == run.id).order_by(VerificationAttempt.file_path, VerificationAttempt.function_qualname).all()
    events = db.query(JobEvent).filter(JobEvent.run_id == run.id).order_by(JobEvent.ts).all()
    diff_artifact = Path(settings.data_path()) / "artifacts" / str(run.id) / "unified.diff"
    diff_text = diff_artifact.read_text(encoding="utf-8", errors="replace") if diff_artifact.exists() else ""
    return {
        "report_type": "branchsleuth.evidence",
        "report_version": 1,
        "generated_at": utcnow().isoformat(),
        "analysis": {
            "id": str(run.id),
            "repository": {"id": str(repo.id), "name": repo.name, "source_type": repo.source_type},
            "baseline_ref": run.baseline_ref,
            "target_ref": run.target_ref,
            "resolved_baseline": run.resolved_baseline_sha,
            "resolved_target": run.resolved_target_sha,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "duration_seconds": run.duration_seconds,
            "options": run.options,
            "summary": run.summary,
            "runtime": run.runtime_info,
            "error": run.error_message,
        },
        "changed_files": [
            {
                "path": f.path,
                "old_path": f.old_path,
                "change_type": f.change_type,
                "language": f.language,
                "supported": f.supported,
                "parse_error": f.parse_error,
                "added_lines": f.added_lines,
                "removed_lines": f.removed_lines,
                "coverage": f.coverage,
                "scopes": [
                    {
                        "qualname": s.qualname,
                        "kind": s.kind,
                        "lines": [s.start_line, s.end_line],
                        "changed_lines": s.changed_lines,
                        "coverage_status": s.coverage_status,
                        "covered_changed_lines": s.covered_changed_lines,
                        "uncovered_changed_lines": s.uncovered_changed_lines,
                    }
                    for s in f.scopes
                ],
            }
            for f in files
        ],
        "tests": [
            {
                "node_id": t.node_id,
                "baseline_outcome": t.baseline_outcome,
                "modified_outcome": t.modified_outcome,
                "category": t.category,
                "executed_changed_lines": t.executed_changed_lines,
                "error_excerpt": t.error_excerpt,
            }
            for t in tests
        ],
        "verifications": [
            {
                "id": str(a.id),
                "file": a.file_path,
                "function": a.function_qualname,
                "kind": a.kind,
                "classification": a.classification,
                "rationale": a.rationale,
                "input": a.input_payload,
                "baseline_outcome": a.baseline_outcome,
                "modified_outcome": a.modified_outcome,
                "property_code": a.property_code,
                "reproducible": a.reproducible,
                "minimized": a.minimized,
                "environment": a.environment,
                "detail": a.detail,
            }
            for a in attempts
        ],
        "events": [
            {"ts": e.ts.isoformat(), "level": e.level, "stage": e.stage, "message": e.message}
            for e in events
        ],
        "unified_diff": diff_text[:200_000],
    }


def _md_outcome(v) -> str:
    return v if v else "not_run"


def build_report_markdown(db: Session, run: AnalysisRun, repo: Repository) -> str:
    data = build_report_json(db, run, repo)
    lines: list[str] = []
    a = data["analysis"]
    lines.append("# BranchSleuth Evidence Report")
    lines.append("")
    lines.append(f"- **Repository**: {repo.name} ({repo.source_type})")
    lines.append(f"- **Analysis ID**: {run.id}")
    lines.append(f"- **Baseline**: `{run.baseline_ref}` → `{run.resolved_baseline_sha}`")
    lines.append(f"- **Target**: `{run.target_ref}` → `{run.resolved_target_sha}`")
    lines.append(f"- **Status**: {run.status}" + (f" — {run.error_message}" if run.error_message else ""))
    lines.append(f"- **Duration**: {run.duration_seconds:.1f}s" if run.duration_seconds else "- **Duration**: n/a")
    runtime = a.get("runtime") or {}
    lines.append(f"- **Runtime verification**: {'executed in isolated Docker worker' if runtime.get('docker') else 'NOT executed (static analysis only)'}")
    if runtime.get("python_version"):
        lines.append(f"- **Worker Python**: {runtime['python_version']}")
    lines.append("")
    summary = a.get("summary") or {}
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---|")
    lines.append(f"| Changed files | {summary.get('changed_files', 0)} |")
    lines.append(f"| Changed scopes | {summary.get('changed_scopes', 0)} |")
    lines.append(f"| Uncovered changed lines | {summary.get('uncovered_changed_lines', 0)} |")
    cats = (summary.get("tests") or {}).get("categories") or {}
    for cat in ("REGRESSION", "PREEXISTING_FAILURE", "FIXED", "STABLE_PASS"):
        lines.append(f"| Tests {cat.replace('_', ' ').lower()} | {cats.get(cat, 0)} |")
    classifications = (summary.get("verifications") or {}).get("classifications") or {}
    for cls in ("PROVEN_FAILURE", "BEHAVIOR_DIVERGENCE", "VERIFIED_CHECK_PASSED", "INCONCLUSIVE"):
        lines.append(f"| Verifications {cls} | {classifications.get(cls, 0)} |")
    lines.append("")
    lines.append("## Changed code and coverage")
    lines.append("")
    for f in data["changed_files"]:
        lines.append(f"### `{f['path']}` ({f['change_type']})")
        if f.get("parse_error"):
            lines.append(f"- Parse error: {f['parse_error']}")
        cov = f.get("coverage") or {}
        if cov.get("available"):
            exec_lines = [k for k, v in (cov.get("lines") or {}).items() if v["status"] == "CHANGED_AND_EXECUTED"]
            unexec_lines = [k for k, v in (cov.get("lines") or {}).items() if v["status"] == "CHANGED_NOT_EXECUTED"]
            lines.append(f"- Changed lines executed by tests: {len(exec_lines)}")
            if unexec_lines:
                lines.append(f"- Changed lines with no executing test: {', '.join(unexec_lines)}")
        else:
            lines.append(f"- Coverage: {cov.get('reason', 'unavailable')}")
        for s in f.get("scopes", []):
            lines.append(
                f"- `{s['qualname']}` ({s['kind']}, lines {s['lines'][0]}–{s['lines'][1]}): changed lines {s['changed_lines']}, coverage {s['coverage_status']}"
            )
        lines.append("")
    lines.append("## Test outcomes")
    lines.append("")
    if data["tests"]:
        lines.append("| Test | Baseline | Target | Category |")
        lines.append("|---|---|---|---|")
        for t in data["tests"]:
            lines.append(f"| `{t['node_id']}` | {_md_outcome(t['baseline_outcome'])} | {_md_outcome(t['modified_outcome'])} | {t['category']} |")
    else:
        lines.append("_No test results were recorded for this run._")
    lines.append("")
    lines.append("## Targeted verification")
    lines.append("")
    if data["verifications"]:
        for v in data["verifications"]:
            lines.append(f"### `{v['function']}` in `{v['file']}` — {v['classification']}")
            lines.append(f"- Kind: {v['kind']}")
            lines.append(f"- Rationale: {v['rationale']}")
            if v.get("input"):
                lines.append(f"- Input: `{json.dumps(v['input'])}`")
            if v.get("baseline_outcome"):
                lines.append(f"- Baseline outcome: `{json.dumps(v['baseline_outcome'])}`")
            if v.get("modified_outcome"):
                lines.append(f"- Target outcome: `{json.dumps(v['modified_outcome'])}`")
            if v.get("property_code"):
                lines.append("")
                lines.append("Property checked:")
                lines.append("```python")
                lines.append(v["property_code"])
                lines.append("```")
            if v.get("reproducible") is not None:
                lines.append(f"- Reproduced: {v['reproducible']}")
            lines.append("")
    else:
        lines.append("_No targeted verification attempts were recorded._")
        lines.append("")
    lines.append("## Reproduction")
    lines.append("")
    lines.append(
        "To reproduce: clone the repository, check out the target revision "
        f"`{run.resolved_target_sha}`, and re-run the inputs listed in the targeted verification section."
    )
    lines.append("")
    lines.append("## Diff")
    lines.append("")
    lines.append("```diff")
    lines.append(data.get("unified_diff", "")[:100_000])
    lines.append("```")
    return "\n".join(lines)
