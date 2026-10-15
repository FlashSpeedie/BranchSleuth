from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DbDep, RateLimitDep, get_workspace, require_api_key
from app.config import settings
from app.db.models import RepoSnapshot, RepoSource, Repository, utcnow
from app.schemas.schemas import (
    RepositoryCreate,
    RepositoryListOut,
    RepositoryOut,
    RefOut,
    SnapshotInfo,
)
from app.services import git_service
from app.services.archive_service import ArchiveValidationError, extract_zip_safely
from app.services.security import UrlValidationError, validate_git_url

router = APIRouter(prefix="/repositories", dependencies=[RateLimitDep, Depends(require_api_key)])


def _repo_out(db: Session, repo: Repository) -> RepositoryOut:
    count = db.scalar(select(func.count(RepoSnapshot.id)).where(RepoSnapshot.repository_id == repo.id))
    out = RepositoryOut.model_validate(repo)
    out.snapshot_count = count or 0
    return out


def _get_repo(db: Session, repo_id: uuid.UUID) -> Repository:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="repository not found")
    return repo


@router.post("", response_model=RepositoryOut, status_code=201)
def create_repository(payload: RepositoryCreate, db=DbDep) -> RepositoryOut:
    ws = get_workspace(db)
    if payload.git_url:
        try:
            parsed = validate_git_url(payload.git_url)
        except UrlValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))
        repo = Repository(
            workspace_id=ws.id,
            name=payload.name,
            source_type=RepoSource.GIT_URL.value,
            url=parsed.https_url,
        )
    elif payload.local_path:
        if not settings.allow_local_repos:
            raise HTTPException(status_code=403, detail="local repositories are not enabled on this server")
        path = Path(payload.local_path)
        if not path.is_dir():
            raise HTTPException(status_code=422, detail="local path is not a directory")
        if not (path / ".git").exists():
            raise HTTPException(status_code=422, detail="local path is not a git repository")
        resolved = path.resolve()
        repo = Repository(
            workspace_id=ws.id,
            name=payload.name,
            source_type=RepoSource.LOCAL.value,
            local_path=str(resolved),
        )
    else:
        raise HTTPException(status_code=422, detail="provide git_url or local_path")
    db.add(repo)
    db.commit()
    return _repo_out(db, repo)


@router.post("/upload", response_model=RepositoryOut, status_code=201)
async def upload_repository(
    db=DbDep,
    name: str = Form(...),
    file: UploadFile = File(...),
) -> RepositoryOut:
    ws = get_workspace(db)
    upload_dir = Path(settings.data_path()) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    zip_path = upload_dir / f"{uuid.uuid4().hex}.zip"
    size = 0
    try:
        with open(zip_path, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail=f"upload exceeds {settings.max_upload_bytes} bytes")
                fh.write(chunk)
        snapshot_root = Path(settings.data_path()) / "snapshots" / uuid.uuid4().hex
        try:
            extract_zip_safely(zip_path, snapshot_root)
        except ArchiveValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))
    finally:
        zip_path.unlink(missing_ok=True)
    entries = [p for p in snapshot_root.rglob("*") if p.is_file()]
    if len(entries) == 1 and entries[0].name.endswith(".zip"):
        raise HTTPException(status_code=422, detail="nested zip archives are not supported")
    top = snapshot_root
    if len([p for p in snapshot_root.iterdir()]) == 1 and (snapshot_root / next(iter(snapshot_root.iterdir()))).is_dir():
        candidate = next(iter(snapshot_root.iterdir()))
        nested = [p for p in candidate.rglob("*") if p.is_file()]
        if nested:
            top = candidate
    repo = Repository(
        workspace_id=ws.id,
        name=name.strip()[:255],
        source_type=RepoSource.UPLOAD.value,
    )
    db.add(repo)
    db.flush()
    snap = RepoSnapshot(
        repository_id=repo.id,
        label="snapshot-1",
        storage_path=str(top.resolve()),
        file_count=len(entries),
    )
    db.add(snap)
    db.commit()
    return _repo_out(db, repo)


@router.post("/{repo_id}/snapshots", response_model=SnapshotInfo, status_code=201)
async def upload_snapshot(repo_id: uuid.UUID, db=DbDep, file: UploadFile = File(...)) -> SnapshotInfo:
    repo = _get_repo(db, repo_id)
    if repo.source_type != RepoSource.UPLOAD.value:
        raise HTTPException(status_code=409, detail="snapshots can only be added to uploaded repositories")
    count = db.scalar(select(func.count(RepoSnapshot.id)).where(RepoSnapshot.repository_id == repo.id))
    upload_dir = Path(settings.data_path()) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    zip_path = upload_dir / f"{uuid.uuid4().hex}.zip"
    size = 0
    try:
        with open(zip_path, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail=f"upload exceeds {settings.max_upload_bytes} bytes")
                fh.write(chunk)
        snapshot_root = Path(settings.data_path()) / "snapshots" / uuid.uuid4().hex
        try:
            extract_zip_safely(zip_path, snapshot_root)
        except ArchiveValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))
    finally:
        zip_path.unlink(missing_ok=True)
    entries = [p for p in snapshot_root.rglob("*") if p.is_file()]
    top = snapshot_root
    if len(list(snapshot_root.iterdir())) == 1 and next(iter(snapshot_root.iterdir())).is_dir():
        candidate = next(iter(snapshot_root.iterdir()))
        if [p for p in candidate.rglob("*") if p.is_file()]:
            top = candidate
    snap = RepoSnapshot(
        repository_id=repo.id,
        label=f"snapshot-{(count or 0) + 1}",
        storage_path=str(top.resolve()),
        file_count=len(entries),
    )
    db.add(snap)
    repo.updated_at = utcnow()
    db.commit()
    db.refresh(snap)
    return SnapshotInfo(id=snap.id, label=snap.label, file_count=snap.file_count, created_at=snap.created_at)


@router.get("", response_model=RepositoryListOut)
def list_repositories(db=DbDep, limit: int = 50, offset: int = 0) -> RepositoryListOut:
    limit = max(1, min(limit, 100))
    total = db.scalar(select(func.count(Repository.id)))
    repos = db.scalars(select(Repository).order_by(Repository.created_at.desc()).offset(offset).limit(limit)).all()
    return RepositoryListOut(items=[_repo_out(db, r) for r in repos], total=total or 0)


@router.get("/{repo_id}", response_model=RepositoryOut)
def get_repository(repo_id: uuid.UUID, db=DbDep) -> RepositoryOut:
    return _repo_out(db, _get_repo(db, repo_id))


@router.get("/{repo_id}/refs", response_model=list[RefOut])
def list_refs(repo_id: uuid.UUID, db=DbDep) -> list[RefOut]:
    repo = _get_repo(db, repo_id)
    refs: list[RefOut] = []
    if repo.source_type == RepoSource.UPLOAD.value:
        snaps = db.scalars(select(RepoSnapshot).where(RepoSnapshot.repository_id == repo.id).order_by(RepoSnapshot.created_at)).all()
        for s in snaps:
            refs.append(RefOut(name=s.label, sha=s.id.hex))
        return refs
    if repo.source_type == RepoSource.GIT_URL.value:
        assert repo.url is not None
        try:
            raw = git_service.ls_remote(repo.url, is_local=False, timeout=60)
        except git_service.GitError as e:
            raise HTTPException(status_code=502, detail=str(e)[:300])
    else:
        assert repo.local_path is not None
        try:
            raw = git_service.ls_remote(repo.local_path, is_local=True, timeout=30)
        except git_service.GitError as e:
            raise HTTPException(status_code=502, detail=str(e)[:300])
    for ref, sha in raw[:200]:
        short = ref.replace("refs/heads/", "").replace("refs/tags/", "")
        refs.append(RefOut(name=short, sha=sha))
    return refs
