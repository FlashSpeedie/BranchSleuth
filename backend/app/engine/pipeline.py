from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
import uuid
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import (
    AnalysisRun,
    Artifact,
    ChangedFile,
    ChangedScope,
    JobEvent,
    Repository,
    RepoSnapshot,
    RunStatus,
    TestRecord,
    VerificationAttempt,
    utcnow,
)
from app.engine.snapshot_diff import snapshot_unified_diff
from app.services import git_service
from app.services.ast_analyzer import analyze_signature, build_scope_index, extract_boundary_constants
from app.services.classifier import classify_probe_result, classify_test_pair
from app.services.coverage_service import load_coverage, match_test
from app.services.diff_parser import parse_unified_diff

logger = logging.getLogger("branchsleuth.pipeline")


class PipelineCancelled(Exception):
    pass


class PipelineError(Exception):
    def __init__(self, message: str, kind: str = "error"):
        super().__init__(message)
        self.kind = kind


def _add_event(db: Session, run_id: uuid.UUID, stage: str, message: str, level: str = "info", detail: dict | None = None) -> None:
    db.add(JobEvent(run_id=run_id, stage=stage, message=message[:4000], level=level, detail=detail or {}))


def _set_stage(db: Session, run: AnalysisRun, status: str | None, stage: str, detail: str) -> None:
    if status:
        run.status = status
    run.stage = stage
    run.stage_detail = detail[:2000]
    db.add(run)
    db.commit()


def _sha_for_dir(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            h.update(path.relative_to(root).as_posix().encode())
            h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()[:40]


def _resolve_sources(db: Session, run: AnalysisRun, repo: Repository, work: Path) -> dict:
    refs: dict = {}
    if repo.source_type == "upload":
        snaps = list(db.scalars(select(RepoSnapshot).where(RepoSnapshot.repository_id == repo.id).order_by(RepoSnapshot.created_at)))
        if not snaps:
            raise PipelineError("repository has no uploaded snapshots", kind="input")
        if len(snaps) < 2:
            raise PipelineError("repository needs at least two snapshots to compare", kind="input")
        by_label = {s.label: s for s in snaps}
        base_snap = by_label.get(run.baseline_ref or "", snaps[0])
        target_snap = by_label.get(run.target_ref or "", snaps[-1])
        if base_snap is target_snap:
            raise PipelineError("baseline and target snapshots must differ", kind="input")
        refs["baseline_dir"] = Path(base_snap.storage_path)
        refs["modified_dir"] = Path(target_snap.storage_path)
        refs["baseline_sha"] = f"upload-{base_snap.label}"
        refs["target_sha"] = f"upload-{target_snap.label}"
        refs["diff_text"] = snapshot_unified_diff(refs["baseline_dir"], refs["modified_dir"])
        refs["git_repo"] = None
        return refs

    if repo.source_type == "git_url":
        assert repo.url is not None
        clone_dir = work / "clone"
        git_service.clone(repo.url, clone_dir)
        git_repo = str(clone_dir)
    elif repo.source_type == "local" and repo.local_path:
        git_repo = repo.local_path
    else:
        raise PipelineError(f"unsupported repository source type: {repo.source_type}", kind="input")

    default_branch = repo.default_branch or git_service.detect_default_branch(git_repo, is_local=repo.source_type == "local")
    target_ref = run.target_ref or default_branch or "HEAD"
    target_sha = git_service.resolve_ref(git_repo, target_ref)
    baseline_ref = run.baseline_ref or f"{target_sha}~1"
    try:
        baseline_sha = git_service.resolve_ref(git_repo, baseline_ref)
    except git_service.GitError:
        raise PipelineError(f"baseline revision {baseline_ref} could not be resolved (is the target the first commit?)", kind="input")
    refs["git_repo"] = git_repo
    refs["baseline_sha"] = baseline_sha
    refs["target_sha"] = target_sha
    baseline_dir = work / "baseline"
    modified_dir = work / "modified"
    git_service.extract_snapshot(git_repo, baseline_sha, baseline_dir)
    git_service.extract_snapshot(git_repo, target_sha, modified_dir)
    refs["baseline_dir"] = baseline_dir
    refs["modified_dir"] = modified_dir
    refs["diff_text"] = git_service.diff_revisions(git_repo, baseline_sha, target_sha)
    return refs


def _store_artifact(db: Session, run_id: uuid.UUID, kind: str, rel_dir: Path, name: str, data: bytes, content_type: str) -> Artifact:
    rel = f"artifacts/{run_id}/{name}"
    full = Path(settings.data_path()) / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(data)
    art = Artifact(run_id=run_id, kind=kind, rel_path=rel, size_bytes=len(data), content_type=content_type)
    db.add(art)
    return art


def _analyze_changes(db: Session, run: AnalysisRun, refs: dict) -> list[ChangedFile]:
    diff_text: str = refs["diff_text"]
    _store_artifact(db, run.id, "diff", Path(), "unified.diff", diff_text.encode("utf-8", "replace"), "text/plain")
    file_diffs = parse_unified_diff(diff_text)
    rows: list[ChangedFile] = []
    baseline_dir: Path = refs["baseline_dir"]
    modified_dir: Path = refs["modified_dir"]
    for fd in file_diffs:
        if fd.is_binary:
            row = ChangedFile(
                run_id=run.id,
                path=fd.path,
                old_path=fd.old_path,
                change_type=fd.change_type,
                language=None,
                supported=False,
                parse_error="binary file",
                added_lines=sorted(fd.added_lines),
                removed_lines=sorted(fd.removed_lines),
            )
            db.add(row)
            db.flush()
            rows.append(row)
            continue
        is_python = fd.path.endswith(".py")
        language = "python" if is_python else fd.path.rsplit(".", 1)[-1].lower() if "." in fd.path else None
        row = ChangedFile(
            run_id=run.id,
            path=fd.path,
            old_path=fd.old_path,
            change_type=fd.change_type,
            language=language,
            supported=is_python,
            parse_error=None,
            added_lines=sorted(fd.added_lines),
            removed_lines=sorted(fd.removed_lines),
        )
        db.add(row)
        db.flush()
        rows.append(row)
        if not is_python:
            continue
        new_source_path = modified_dir / fd.path
        old_source_path = baseline_dir / (fd.old_path or fd.path)
        new_src = new_source_path.read_text(encoding="utf-8", errors="replace") if new_source_path.exists() else None
        old_src = old_source_path.read_text(encoding="utf-8", errors="replace") if old_source_path.exists() else None
        if fd.change_type != "deleted" and new_src is None:
            row.parse_error = "changed file missing from target snapshot"
            continue
        new_index = build_scope_index(new_src) if new_src is not None else None
        if new_index is not None and new_index.parse_error:
            row.parse_error = f"target revision: {new_index.parse_error}"
        old_index = build_scope_index(old_src) if old_src is not None else None
        if old_index is not None and old_index.parse_error:
            row.parse_error = (row.parse_error + "; " if row.parse_error else "") + f"baseline revision: {old_index.parse_error}"

        scope_by_qualname: dict[str, ChangedScope] = {}

        def scope_row(qualname: str, kind: str, name: str, start: int, end: int, executable: list[int]) -> ChangedScope:
            if qualname in scope_by_qualname:
                return scope_by_qualname[qualname]
            sc = ChangedScope(
                file_id=row.id,
                run_id=run.id,
                kind=kind,
                name=name,
                qualname=qualname,
                start_line=start,
                end_line=end,
                changed_lines=[],
                executable_lines=executable,
            )
            db.add(sc)
            scope_by_qualname[qualname] = sc
            return sc

        added = set(fd.added_lines)
        if new_index is not None:
            for line in sorted(added):
                scope = new_index.find_scope(line)
                if scope is None:
                    continue
                sc = scope_row(scope.qualname, scope.kind, scope.name, scope.start_line, scope.end_line, sorted(scope.executable_lines))
                sc.changed_lines.append(line)
            if added and new_src is not None and all(new_index.find_scope(ln) is None for ln in added):
                sc = scope_row("<module>", "module", fd.path, 1, len(new_src.splitlines()) + 1, [])
                sc.changed_lines.extend(sorted(added))
        removed = set(fd.removed_lines)
        if old_index is not None and removed:
            for line in sorted(removed):
                scope = old_index.find_scope(line)
                if scope is None:
                    continue
                existing = scope_by_qualname.get(scope.qualname)
                if existing is not None:
                    continue
                scope_row(scope.qualname, scope.kind, scope.name, scope.start_line, scope.end_line, [])
    db.flush()
    return rows


def _probe_targets(db: Session, run: AnalysisRun, files: list[ChangedFile], modified_dir: Path) -> list[dict]:
    options = run.options or {}
    property_code = options.get("property_code")
    property_target = options.get("property_target")
    max_examples = int(options.get("hypothesis_max_examples", settings.hypothesis_max_examples))
    deadline_ms = int(options.get("hypothesis_deadline_ms", settings.hypothesis_deadline_ms))
    targets: list[dict] = []
    for row in files:
        if not row.supported or row.change_type == "deleted" or row.parse_error:
            continue
        src_path = modified_dir / row.path
        if not src_path.exists():
            continue
        src = src_path.read_text(encoding="utf-8", errors="replace")
        for scope in row.scopes:
            if scope.kind not in ("function", "async_function"):
                continue
            sig = analyze_signature(src, scope.qualname)
            target_id = str(scope.id)
            entry: dict = {
                "id": target_id,
                "scope_id": str(scope.id),
                "file": row.path,
                "qualname": scope.qualname,
                "params": [],
                "boundaries": [],
                "max_examples": max_examples,
                "deadline_ms": deadline_ms,
            }
            if sig is None:
                entry["unsupported_reason"] = "scope not resolvable in target revision"
            elif not sig.supported:
                entry["unsupported_reason"] = sig.reason or "unsupported signature"
            else:
                typed_params: dict[str, str | None] = {"int": None, "float": None}
                for p in sig.params:
                    strat = p.strategy if isinstance(p.strategy, dict) else p.strategy
                    entry["params"].append(
                        {
                            "name": p.name,
                            "strategy": strat,
                            "has_default": p.has_default,
                            "default": p.default if isinstance(p.default, (int, float, str, bool, type(None))) else None,
                        }
                    )
                    if isinstance(strat, str) and strat in typed_params and typed_params[strat] is None and not p.has_default:
                        typed_params[strat] = p.name
                boundaries = extract_boundary_constants(src, scope.qualname)
                for b in boundaries:
                    param_name = typed_params.get("float") if isinstance(b["to"], float) else typed_params.get("int")
                    if param_name is None:
                        param_name = typed_params.get("int") or typed_params.get("float")
                    entry["boundaries"].append({"param": param_name, "relation": b["relation"], "to": b["to"], "value": b["value"]})
            if property_code and property_target and property_target.strip().lower() == f"{row.path}::{scope.qualname}".strip().lower():
                entry["property_code"] = property_code
            targets.append(entry)
    return targets


def _merge_tests(db: Session, run: AnalysisRun, baseline_result, modified_result, files: list[ChangedFile], cov_facts, src_root: str) -> list[TestRecord]:
    baseline_tests = {t["node_id"]: t for t in baseline_result.tests} if baseline_result else {}
    modified_tests = {t["node_id"]: t for t in modified_result.tests} if modified_result else {}
    all_nodes: dict[str, TestRecord] = {}
    added_by_file = {row.path: set(row.added_lines) for row in files}
    context_to_test: dict[str, list[str]] = defaultdict(list)
    if cov_facts is not None and not cov_facts.error:
        for ctx in cov_facts.contexts:
            if not ctx:
                continue
            matches = [nid for nid in modified_tests if match_test(ctx, nid, modified_tests[nid]["name"])]
            context_to_test[ctx] = matches
    for node_id in sorted(set(baseline_tests) | set(modified_tests)):
        b = baseline_tests.get(node_id)
        m = modified_tests.get(node_id)
        category = classify_test_pair(b["outcome"] if b else None, m["outcome"] if m else None)
        executed: dict[str, list[int]] = {}
        if m and cov_facts is not None and not cov_facts.error:
            for row in files:
                if row.change_type == "deleted" or not row.supported:
                    continue
                container_path = f"{src_root}/{row.path}"
                hits: set[int] = set()
                for ctx in cov_facts.file_context_lines.get(container_path, []):
                    if node_id in context_to_test.get(ctx.context, []):
                        hits |= (ctx.lines or set()) & added_by_file.get(row.path, set())
                if hits:
                    executed[row.path] = sorted(hits)
        rec = TestRecord(
            run_id=run.id,
            node_id=node_id,
            name=node_id.split("::")[-1],
            baseline_outcome=b["outcome"] if b else None,
            modified_outcome=m["outcome"] if m else None,
            category=category,
            duration_ms=((m or b) or {}).get("duration", 0.0) * 1000,
            error_excerpt=((m or b) or {}).get("error_excerpt"),
            executed_changed_lines=executed,
            ran_changed_code=bool(executed),
        )
        db.add(rec)
        all_nodes[node_id] = rec
    return list(all_nodes.values())


def _apply_coverage(db: Session, run: AnalysisRun, files: list[ChangedFile], cov_facts, tests: list[TestRecord], src_root: str) -> None:
    available = cov_facts is not None and not cov_facts.error
    test_by_node: dict[str, TestRecord] = {t.node_id: t for t in tests}
    context_to_node: dict[str, list[str]] = defaultdict(list)
    ambiguous = False
    if available:
        for ctx in cov_facts.contexts:
            if not ctx:
                continue
            matches = [nid for nid in test_by_node if match_test(ctx, nid, nid.split("::")[-1])]
            if len(matches) > 1 and "::" not in ctx:
                ambiguous = True
            context_to_node[ctx] = matches
    executable_cache: dict[str, set[int]] = {}
    for row in files:
        line_status: dict[str, dict] = {}
        if not row.supported or row.change_type == "deleted":
            row.coverage = {"available": False, "reason": "coverage not applicable to this file"}
            continue
        new_path = Path(src_root) / row.path
        executable: set[int] = set()
        for scope in row.scopes:
            executable.update(scope.executable_lines or [])
        executable_cache[row.path] = executable
        if not available:
            row.coverage = {
                "available": False,
                "reason": cov_facts.error if cov_facts else "coverage collection unavailable",
                "lines": {},
            }
            for scope in row.scopes:
                scope.coverage_status = "COVERAGE_UNAVAILABLE"
                scope.covered_changed_lines = []
                scope.uncovered_changed_lines = []
            continue
        container_path = str(new_path).replace("\\", "/")
        executed_by_line: dict[int, list[str]] = defaultdict(list)
        for ctx_lines in cov_facts.file_context_lines.get(container_path, []):
            for line in ctx_lines.lines or []:
                for nid in context_to_node.get(ctx_lines.context, []):
                    executed_by_line[line].append(nid)
        for line in sorted(set(row.added_lines) | set(row.removed_lines)):
            key = str(line)
            if line in row.removed_lines and line not in row.added_lines:
                line_status[key] = {"status": "REMOVED_LINE", "tests": []}
                continue
            if line not in row.added_lines:
                continue
            runners = sorted(set(executed_by_line.get(line, [])))
            is_executable = line in executable
            if not is_executable:
                line_status[key] = {"status": "NOT_EXECUTABLE_CODE", "tests": runners}
            elif runners:
                line_status[key] = {"status": "CHANGED_AND_EXECUTED", "tests": runners}
            else:
                line_status[key] = {"status": "CHANGED_NOT_EXECUTED", "tests": []}
        row.coverage = {"available": True, "ambiguous_context": ambiguous, "lines": line_status}
        for scope in row.scopes:
            added_in_scope = set(scope.changed_lines or [])
            if not added_in_scope:
                scope.coverage_status = "NO_NEW_EXECUTABLE_LINES"
                scope.covered_changed_lines = []
                scope.uncovered_changed_lines = []
                continue
            covered = {ln for ln in added_in_scope if line_status.get(str(ln), {}).get("status") == "CHANGED_AND_EXECUTED"}
            executable_in_scope = added_in_scope & (set(scope.executable_lines or []) | set(scope.changed_lines or []))
            non_exec = {ln for ln in added_in_scope if line_status.get(str(ln), {}).get("status") == "NOT_EXECUTABLE_CODE"}
            covered_effective = covered
            to_cover = executable_in_scope - non_exec
            if to_cover and covered_effective >= to_cover:
                scope.coverage_status = "CHANGED_AND_EXECUTED"
            elif to_cover:
                scope.coverage_status = "CHANGED_NOT_EXECUTED"
            else:
                scope.coverage_status = "NO_NEW_EXECUTABLE_LINES"
            scope.covered_changed_lines = sorted(covered)
            scope.uncovered_changed_lines = sorted(to_cover - covered_effective)


def _record_probes(db: Session, run: AnalysisRun, targets: list[dict], probe_payload: dict, env_meta: dict) -> list[VerificationAttempt]:
    attempts: list[VerificationAttempt] = []
    results = probe_payload.get("targets", {}) if probe_payload else {}
    timed_out = probe_payload.get("timed_out", False) if probe_payload else False
    for target in targets:
        scope_id = target.get("scope_id")
        probe_result = results.get(target["id"])
        if probe_result is None:
            probe_result = {"status": "timeout" if timed_out else "environment_error", "reason": "probe produced no result" + (" (container timed out)" if timed_out else "")}
        classification, rationale = classify_probe_result(probe_result)
        attempt = VerificationAttempt(
            run_id=run.id,
            scope_id=uuid.UUID(scope_id) if scope_id else None,
            file_path=target["file"],
            function_qualname=target["qualname"],
            kind="property_probe" if target.get("property_code") else "differential_probe",
            classification=classification,
            rationale=rationale,
            input_payload=probe_result.get("input"),
            baseline_outcome=probe_result.get("baseline_outcome"),
            modified_outcome=probe_result.get("modified_outcome"),
            property_code=target.get("property_code"),
            reproducible=probe_result.get("reproducible"),
            minimized=bool(probe_result.get("minimized")),
            environment={
                "worker_image": settings.worker_image,
                "network": "disabled",
                "user": "nobody",
                "python_version": env_meta.get("python_version"),
                "dependencies": env_meta.get("dependencies"),
            },
            detail={
                "status": probe_result.get("status"),
                "via": probe_result.get("via"),
                "examples_run": probe_result.get("examples_run"),
                "property_checked": probe_result.get("property_checked"),
                "property_held": probe_result.get("property_held"),
                "boundary_candidates": len(target.get("boundaries", [])),
                "reason": probe_result.get("reason"),
            },
        )
        db.add(attempt)
        attempts.append(attempt)
    return attempts


def execute_analysis(run_id, session_factory: sessionmaker, cancel_check=None) -> None:
    db: Session = session_factory()
    work: Path | None = None
    run_key = str(run_id)[:12]
    try:
        run = db.get(AnalysisRun, run_id)
        if run is None:
            raise PipelineError(f"analysis run {run_id} not found")
        repo = db.get(Repository, run.repository_id)
        if repo is None:
            raise PipelineError("repository record missing")

        def check_cancel() -> None:
            if cancel_check is not None and cancel_check():
                raise PipelineCancelled()
            run.heartbeat_at = utcnow()
            db.add(run)
            db.commit()

        started = time.time()
        run.started_at = run.started_at or utcnow()
        _set_stage(db, run, RunStatus.PREPARING.value, "preparing", "resolving revisions and preparing snapshots")
        _add_event(db, run.id, "preparing", "analysis started")

        work = Path(settings.data_path()) / "tmp" / run_key
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)

        refs = _resolve_sources(db, run, repo, work)
        check_cancel()
        run.resolved_baseline_sha = refs["baseline_sha"]
        run.resolved_target_sha = refs["target_sha"]
        db.add(run)
        db.commit()
        _add_event(db, run.id, "preparing", f"revisions resolved: baseline={refs['baseline_sha'][:12]} target={refs['target_sha'][:12]}")

        _set_stage(db, run, RunStatus.ANALYZING.value, "analyzing", "parsing diff and mapping changed scopes")
        files = _analyze_changes(db, run, refs)
        db.commit()
        _add_event(db, run.id, "analyzing", f"diff parsed: {len(files)} changed files", detail={"files": [f.path for f in files][:50]})
        check_cancel()

        options = run.options or {}
        baseline_result = None
        modified_result = None
        cov_facts = None
        probe_payload: dict = {}
        targets: list[dict] = []
        env_meta: dict = {}
        runtime_status = "skipped"
        runtime_note = ""
        tests: list[TestRecord] = []

        want_runtime = options.get("targeted_verification", True) or options.get("run_baseline_tests", True) or options.get("run_modified_tests", True)
        if want_runtime:
            _set_stage(db, run, RunStatus.VERIFYING.value, "verifying", "starting isolated runtime verification")
            try:
                from app.worker_runtime.docker_worker import WorkerSession

                with WorkerSession(run_key=run_key) as worker:
                    worker.prepare(refs["baseline_dir"], refs["modified_dir"])
                    check_cancel()
                    _set_stage(db, run, None, "verifying", "running baseline test suite in isolated container")
                    if options.get("run_baseline_tests", True):
                        baseline_result = worker.run_tests("/bs/baseline", "baseline")
                        _add_event(db, run.id, "verifying", f"baseline tests: {baseline_result.outcome} ({len(baseline_result.tests)} tests)")
                    check_cancel()
                    _set_stage(db, run, None, "verifying", "running modified test suite in isolated container")
                    if options.get("run_modified_tests", True):
                        modified_result = worker.run_tests("/bs/modified", "modified")
                        _add_event(db, run.id, "verifying", f"modified tests: {modified_result.outcome} ({len(modified_result.tests)} tests)")
                    check_cancel()
                    env_meta = modified_result.env_meta if modified_result is not None else baseline_result.env_meta if baseline_result is not None else {}
                    if options.get("collect_coverage", True) and modified_result is not None and modified_result.coverage_file is not None:
                        cov_facts = load_coverage(str(modified_result.coverage_file))
                        if cov_facts.error:
                            _add_event(db, run.id, "verifying", f"coverage unavailable: {cov_facts.error}", level="warn")
                    targets = _probe_targets(db, run, files, refs["modified_dir"])
                    if options.get("targeted_verification", True) and targets:
                        _set_stage(db, run, None, "verifying", f"running targeted verification for {len(targets)} changed functions")
                        spec = {
                            "spec_revision": "1",
                            "max_examples": int(options.get("hypothesis_max_examples", settings.hypothesis_max_examples)),
                            "targets": targets,
                        }
                        probe_payload = worker.run_probes(spec)
                        n_results = len(probe_payload.get("targets", {}))
                        _add_event(db, run.id, "verifying", f"targeted verification produced evidence for {n_results}/{len(targets)} functions")
                    runtime_status = "executed"
                if baseline_result is not None and baseline_result.coverage_file is not None:
                    _store_artifact(db, run.id, "coverage_db", Path(), "baseline.coverage", baseline_result.coverage_file.read_bytes(), "application/octet-stream")
                if modified_result is not None and modified_result.coverage_file is not None:
                    _store_artifact(db, run.id, "coverage_db", Path(), "modified.coverage", modified_result.coverage_file.read_bytes(), "application/octet-stream")
                if probe_payload:
                    _store_artifact(db, run.id, "probe_results", Path(), "probe_results.json", json.dumps(probe_payload).encode(), "application/json")
                for phase, res in (("baseline", baseline_result), ("modified", modified_result)):
                    if res is not None and res.log:
                        _store_artifact(db, run.id, "worker_log", Path(), f"{phase}_tests.log", res.log.encode("utf-8", "replace"), "text/plain")
            except PipelineCancelled:
                raise
            except Exception as e:
                from app.worker_runtime.docker_worker import WorkerUnavailable

                if isinstance(e, WorkerUnavailable):
                    runtime_status = "unavailable"
                    runtime_note = str(e)[:500]
                    _add_event(db, run.id, "verifying", f"runtime verification skipped: {runtime_note}", level="warn")
                else:
                    raise
        else:
            runtime_status = "skipped_by_option"
            runtime_note = "runtime verification disabled for this run"

        _set_stage(db, run, None, "mapping", "mapping per-test coverage onto changed lines")
        tests = _merge_tests(db, run, baseline_result, modified_result, files, cov_facts, "/bs/modified")
        _apply_coverage(db, run, files, cov_facts, tests, "/bs/modified")
        db.commit()
        _add_event(db, run.id, "mapping", f"mapped coverage for {len(tests)} tests")

        _set_stage(db, run, None, "classifying", "classifying verification evidence")
        attempts = _record_probes(db, run, targets, probe_payload, env_meta)
        db.commit()

        categories: dict[str, int] = defaultdict(int)
        for t in tests:
            categories[t.category] += 1
        classifications: dict[str, int] = defaultdict(int)
        for a in attempts:
            classifications[a.classification] += 1
        uncovered_total = sum(len(sc.uncovered_changed_lines or []) for f in files for sc in f.scopes)
        run.summary = {
            "changed_files": len(files),
            "changed_scopes": sum(len(f.scopes) for f in files),
            "uncovered_changed_lines": uncovered_total,
            "tests": {
                "baseline_run": baseline_result is not None,
                "modified_run": modified_result is not None,
                "baseline_outcome": baseline_result.outcome if baseline_result else None,
                "modified_outcome": modified_result.outcome if modified_result else None,
                "count": len(tests),
                "categories": dict(categories),
            },
            "verifications": {
                "attempted": len(attempts),
                "classifications": dict(classifications),
            },
            "runtime_status": runtime_status,
            "runtime_note": runtime_note,
            "proven_failures": classifications.get("PROVEN_FAILURE", 0),
            "behavior_divergences": classifications.get("BEHAVIOR_DIVERGENCE", 0),
            "regressions": categories.get("REGRESSION", 0),
        }
        run.runtime_info = {
            "docker": runtime_status == "executed",
            "worker_image": settings.worker_image if runtime_status == "executed" else None,
            "python_version": env_meta.get("python_version"),
            "dependencies": env_meta.get("dependencies"),
        }
        run.status = RunStatus.COMPLETED.value
        run.stage = "completed"
        run.stage_detail = f"analysis complete: {run.summary['changed_files']} changed files, {run.summary['proven_failures']} confirmed failures"
        run.completed_at = utcnow()
        run.duration_seconds = time.time() - started
        db.add(run)
        _add_event(db, run.id, "completed", f"analysis completed in {run.duration_seconds:.1f}s")
        db.commit()
    except PipelineCancelled:
        _mark_final(db, run_id, session_factory, RunStatus.CANCELLED, "analysis cancelled by request", stage="cancelled")
        return
    except PipelineError as e:
        _mark_final(db, run_id, session_factory, RunStatus.FAILED, str(e)[:2000], stage=e.kind)
        logger.warning("run %s failed: %s", run_id, e)
        return
    except Exception as e:
        logger.exception("pipeline failure for run %s", run_id)
        _mark_final(db, run_id, session_factory, RunStatus.FAILED, f"{type(e).__name__}: {e}"[:2000], stage="error")
        raise
    finally:
        db.close()
        if work is not None:
            shutil.rmtree(work, ignore_errors=True)


def _mark_final(db: Session, run_id, session_factory, status: RunStatus, message: str, stage: str) -> None:
    try:
        run = db.get(AnalysisRun, run_id)
        if run is None or run.status in (RunStatus.COMPLETED.value, RunStatus.CANCELLED.value, RunStatus.FAILED.value):
            return
        run.status = status.value
        run.error_message = message
        run.stage = stage
        run.completed_at = utcnow()
        if run.started_at is not None:
            run.duration_seconds = (utcnow() - run.started_at).total_seconds()
        _add_event(db, run.id, stage, message, level="warn")
        db.add(run)
        db.commit()
    except Exception:
        db.rollback()
