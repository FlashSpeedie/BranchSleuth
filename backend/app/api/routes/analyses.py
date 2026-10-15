from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import DbDep, RateLimitDep, get_workspace, require_api_key
from app.config import settings
from app.db.models import (
    AnalysisRun,
    ChangedFile,
    JobEvent,
    Repository,
    RunStatus,
    TestRecord,
    VerificationAttempt,
    utcnow,
)
from app.jobs.queue import clear_evidence_for_rerun
from app.schemas.schemas import (
    AnalysisCreate,
    AnalysisListOut,
    AnalysisOut,
    ChangedFileOut,
    GraphEdge,
    GraphNode,
    GraphOut,
    JobEventOut,
    TestRecordOut,
    VerificationAttemptOut,
)
from app.services.report_service import build_report_json, build_report_markdown

router = APIRouter(prefix="/analyses", dependencies=[RateLimitDep, Depends(require_api_key)])

ACTIVE = (RunStatus.QUEUED.value, RunStatus.PREPARING.value, RunStatus.ANALYZING.value, RunStatus.VERIFYING.value)

MAX_GRAPH_NODES = 400


def _run_out(db: Session, run: AnalysisRun) -> AnalysisOut:
    out = AnalysisOut.model_validate(run)
    repo = db.get(Repository, run.repository_id)
    out.repository_name = repo.name if repo else None
    return out


def _get_run(db: Session, run_id: uuid.UUID) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="analysis run not found")
    return run


@router.post("", response_model=AnalysisOut, status_code=201)
def create_analysis(payload: AnalysisCreate, db=DbDep) -> AnalysisOut:
    ws = get_workspace(db)
    repo = db.get(Repository, payload.repository_id)
    if repo is None or repo.workspace_id != ws.id:
        raise HTTPException(status_code=404, detail="repository not found")
    duplicate = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.repository_id == repo.id,
            AnalysisRun.status.in_(ACTIVE),
            AnalysisRun.baseline_ref == payload.baseline_ref,
            AnalysisRun.target_ref == payload.target_ref,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=f"an equivalent analysis is already in progress ({duplicate.id})")
    run = AnalysisRun(
        repository_id=repo.id,
        baseline_ref=payload.baseline_ref,
        target_ref=payload.target_ref,
        options=payload.options.model_dump(),
        status=RunStatus.QUEUED.value,
        stage="queued",
        stage_detail="waiting for a worker to pick up this analysis",
    )
    db.add(run)
    db.flush()
    db.add(JobEvent(run_id=run.id, stage="queued", message="analysis created and queued"))
    db.commit()
    return _run_out(db, run)


@router.get("", response_model=AnalysisListOut)
def list_analyses(db=DbDep, limit: int = 25, offset: int = 0, status: str | None = None) -> AnalysisListOut:
    limit = max(1, min(limit, 100))
    query = select(AnalysisRun)
    if status:
        query = query.where(AnalysisRun.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    runs = db.scalars(query.order_by(AnalysisRun.created_at.desc()).offset(offset).limit(limit)).all()
    return AnalysisListOut(items=[_run_out(db, r) for r in runs], total=total or 0)


@router.get("/{run_id}", response_model=AnalysisOut)
def get_analysis(run_id: uuid.UUID, db=DbDep) -> AnalysisOut:
    return _run_out(db, _get_run(db, run_id))


@router.post("/{run_id}/cancel", response_model=AnalysisOut)
def cancel_analysis(run_id: uuid.UUID, db=DbDep) -> AnalysisOut:
    run = _get_run(db, run_id)
    if run.status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value):
        raise HTTPException(status_code=409, detail=f"analysis already {run.status}")
    if run.status == RunStatus.QUEUED.value:
        run.status = RunStatus.CANCELLED.value
        run.stage = "cancelled"
        run.stage_detail = "cancelled before a worker started it"
        run.completed_at = utcnow()
        db.add(JobEvent(run_id=run.id, stage="cancelled", message="analysis cancelled while queued", level="warn"))
    else:
        run.cancel_requested = True
        run.stage_detail = "cancellation requested; waiting for the worker to stop"
        db.add(JobEvent(run_id=run.id, stage="cancelling", message="cancellation requested by user", level="warn"))
    db.add(run)
    db.commit()
    return _run_out(db, run)


@router.post("/{run_id}/retry", response_model=AnalysisOut)
def retry_analysis(run_id: uuid.UUID, db=DbDep) -> AnalysisOut:
    run = _get_run(db, run_id)
    if run.status not in (RunStatus.FAILED.value, RunStatus.CANCELLED.value):
        raise HTTPException(status_code=409, detail=f"analysis in status {run.status} cannot be retried")
    clear_evidence_for_rerun(db, run.id)
    run.status = RunStatus.QUEUED.value
    run.stage = "queued"
    run.stage_detail = "re-queued by user request"
    run.error_message = None
    run.cancel_requested = False
    run.resolved_baseline_sha = None
    run.resolved_target_sha = None
    run.summary = {}
    run.started_at = None
    run.completed_at = None
    run.duration_seconds = None
    db.add(run)
    db.add(JobEvent(run_id=run.id, stage="queued", message="analysis re-queued after failure or cancellation"))
    db.commit()
    return _run_out(db, run)


@router.get("/{run_id}/files", response_model=list[ChangedFileOut])
def list_files(run_id: uuid.UUID, db=DbDep) -> list[ChangedFileOut]:
    run = _get_run(db, run_id)
    files = (
        db.query(ChangedFile)
        .options(joinedload(ChangedFile.scopes))
        .filter(ChangedFile.run_id == run.id)
        .order_by(ChangedFile.path)
        .all()
    )
    return [ChangedFileOut.model_validate(f) for f in files]


@router.get("/{run_id}/files/{file_id}/diff")
def get_file_diff(run_id: uuid.UUID, file_id: uuid.UUID, db=DbDep) -> Response:
    _get_run(db, run_id)
    row = db.get(ChangedFile, file_id)
    if row is None or row.run_id != run_id:
        raise HTTPException(status_code=404, detail="changed file not found")
    diff_artifact = Path(settings.data_path()) / "artifacts" / str(run_id) / "unified.diff"
    if not diff_artifact.exists():
        raise HTTPException(status_code=404, detail="diff artifact not available")
    text = diff_artifact.read_text(encoding="utf-8", errors="replace")
    header = f"diff --git a/{row.old_path or row.path} b/{row.path}"
    start = text.find(header)
    if start == -1:
        raise HTTPException(status_code=404, detail="file not present in unified diff")
    next_start = -1
    for marker in ("\ndiff --git ",):
        next_start = text.find(marker, start + 1)
        if next_start != -1:
            break
    chunk = text[start:next_start] if next_start != -1 else text[start:]
    return Response(content=chunk, media_type="text/plain")


@router.get("/{run_id}/tests", response_model=list[TestRecordOut])
def list_tests(run_id: uuid.UUID, db=DbDep) -> list[TestRecordOut]:
    run = _get_run(db, run_id)
    rows = db.query(TestRecord).filter(TestRecord.run_id == run.id).order_by(TestRecord.node_id).all()
    return [TestRecordOut.model_validate(r) for r in rows]


@router.get("/{run_id}/verifications", response_model=list[VerificationAttemptOut])
def list_verifications(run_id: uuid.UUID, db=DbDep) -> list[VerificationAttemptOut]:
    run = _get_run(db, run_id)
    rows = (
        db.query(VerificationAttempt)
        .filter(VerificationAttempt.run_id == run.id)
        .order_by(VerificationAttempt.file_path, VerificationAttempt.function_qualname)
        .all()
    )
    return [VerificationAttemptOut.model_validate(r) for r in rows]


@router.get("/{run_id}/verifications/{attempt_id}", response_model=VerificationAttemptOut)
def get_verification(run_id: uuid.UUID, attempt_id: uuid.UUID, db=DbDep) -> VerificationAttemptOut:
    _get_run(db, run_id)
    row = db.get(VerificationAttempt, attempt_id)
    if row is None or row.run_id != run_id:
        raise HTTPException(status_code=404, detail="verification attempt not found")
    return VerificationAttemptOut.model_validate(row)


@router.get("/{run_id}/events", response_model=list[JobEventOut])
def list_events(run_id: uuid.UUID, db=DbDep, limit: int = 200) -> list[JobEventOut]:
    run = _get_run(db, run_id)
    limit = max(1, min(limit, 1000))
    rows = db.query(JobEvent).filter(JobEvent.run_id == run.id).order_by(JobEvent.ts).limit(limit).all()
    return [JobEventOut.model_validate(r) for r in rows]


@router.get("/{run_id}/graph", response_model=GraphOut)
def evidence_graph(run_id: uuid.UUID, db=DbDep) -> GraphOut:
    run = _get_run(db, run_id)
    repo = db.get(Repository, run.repository_id)
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    def node(nid: str, ntype: str, label: str, data: dict) -> str:
        nodes.append(GraphNode(id=nid, type=ntype, label=label, data=data))
        return nid

    def edge(src: str, dst: str, etype: str, data: dict | None = None) -> None:
        edges.append(GraphEdge(id=f"{src}->{dst}:{etype}", source=src, target=dst, type=etype, data=data or {}))

    repo_node = node(f"repo:{repo.id}", "repository", repo.name, {"source_type": repo.source_type})
    files = (
        db.query(ChangedFile)
        .options(joinedload(ChangedFile.scopes))
        .filter(ChangedFile.run_id == run.id)
        .order_by(ChangedFile.path)
        .all()
    )
    tests = db.query(TestRecord).filter(TestRecord.run_id == run.id).all()
    attempts = db.query(VerificationAttempt).filter(VerificationAttempt.run_id == run.id).all()
    truncated = False
    line_budget = 200
    for f in files:
        if len(nodes) >= MAX_GRAPH_NODES:
            truncated = True
            break
        fnode = node(f"file:{f.id}", "file", f.path, {"change_type": f.change_type, "supported": f.supported, "language": f.language, "parse_error": f.parse_error})
        edge(repo_node, fnode, "CONTAINS")
        for s in f.scopes:
            if len(nodes) >= MAX_GRAPH_NODES:
                truncated = True
                break
            snode = node(
                f"scope:{s.id}",
                "scope",
                s.qualname,
                {
                    "kind": s.kind,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "changed_lines": s.changed_lines,
                    "coverage_status": s.coverage_status,
                    "covered_changed_lines": s.covered_changed_lines,
                    "uncovered_changed_lines": s.uncovered_changed_lines,
                    "file_path": f.path,
                },
            )
            edge(fnode, snode, "HAS_SCOPE")
        for line, info in (f.coverage or {}).get("lines", {}).items():
            if info.get("status") != "CHANGED_NOT_EXECUTED":
                continue
            if line_budget <= 0 or len(nodes) >= MAX_GRAPH_NODES:
                truncated = True
                break
            line_budget -= 1
            lnode = node(
                f"line:{f.id}:{line}",
                "line",
                f"{f.path}:{line}",
                {"line": int(line), "status": info["status"], "file_path": f.path},
            )
            scope = next((s for s in f.scopes if s.start_line <= int(line) <= s.end_line), None)
            if scope is not None:
                edge(f"scope:{scope.id}", lnode, "HAS_UNCOVERED_LINE")
            else:
                edge(fnode, lnode, "HAS_UNCOVERED_LINE")
    for t in tests:
        if len(nodes) >= MAX_GRAPH_NODES:
            truncated = True
            break
        tnode = node(
            f"test:{t.id}",
            "test",
            t.name,
            {
                "node_id": t.node_id,
                "baseline_outcome": t.baseline_outcome,
                "modified_outcome": t.modified_outcome,
                "category": t.category,
                "executed_changed_lines": t.executed_changed_lines,
            },
        )
        if t.category == "REGRESSION":
            edge(tnode, repo_node, "REGRESSED_AGAINST")
        for path, lines in (t.executed_changed_lines or {}).items():
            f = next((x for x in files if x.path == path), None)
            if f is None:
                continue
            edge(tnode, f"file:{f.id}", "EXECUTED_CHANGED_LINES", {"lines": lines})
            for s in f.scopes:
                if set(s.changed_lines or []) & set(lines):
                    edge(tnode, f"scope:{s.id}", "EXECUTED_CHANGED_SCOPE", {"lines": sorted(set(s.changed_lines or []) & set(lines))})
    for a in attempts:
        if len(nodes) >= MAX_GRAPH_NODES:
            truncated = True
            break
        anode = node(
            f"verify:{a.id}",
            "verification",
            a.function_qualname,
            {
                "classification": a.classification,
                "kind": a.kind,
                "rationale": a.rationale,
                "input": a.input_payload,
                "baseline_outcome": a.baseline_outcome,
                "modified_outcome": a.modified_outcome,
                "reproducible": a.reproducible,
                "file_path": a.file_path,
            },
        )
        if a.scope_id is not None:
            edge(f"scope:{a.scope_id}", anode, "VERIFIED_BY")
        if a.classification == "PROVEN_FAILURE":
            fnode = f"failure:{a.id}"
            nodes.append(
                GraphNode(
                    id=fnode,
                    type="failure",
                    label=f"Confirmed failure: {a.function_qualname}",
                    data={
                        "classification": a.classification,
                        "rationale": a.rationale,
                        "input": a.input_payload,
                        "modified_outcome": a.modified_outcome,
                        "baseline_outcome": a.baseline_outcome,
                        "verification_id": str(a.id),
                    },
                )
            )
            edge(anode, fnode, "PROVES_FAILURE")
    return GraphOut(nodes=nodes, edges=edges, truncated=truncated)


@router.get("/{run_id}/report")
def download_report(run_id: uuid.UUID, db=DbDep, format: str = "md") -> Response:
    run = _get_run(db, run_id)
    repo = db.get(Repository, run.repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository missing")
    safe_id = str(run.id)
    if format == "json":
        data = build_report_json(db, run, repo)
        content = json.dumps(data, indent=2).encode()
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="branchsleuth-{safe_id}.json"'},
        )
    md = build_report_markdown(db, run, repo)
    return Response(
        content=md.encode(),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="branchsleuth-{safe_id}.md"'},
    )
