import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RepoSource(str, enum.Enum):
    GIT_URL = "git_url"
    UPLOAD = "upload"
    LOCAL = "local"


class RunStatus(str, enum.Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    ANALYZING = "analyzing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    repositories: Mapped[list["Repository"]] = relationship(back_populates="workspace")


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(32))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    workspace: Mapped[Workspace] = relationship(back_populates="repositories")
    snapshots: Mapped[list["RepoSnapshot"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    runs: Mapped[list["AnalysisRun"]] = relationship(back_populates="repository")


class RepoSnapshot(Base):
    __tablename__ = "repo_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), index=True)
    label: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(Text)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    repository: Mapped[Repository] = relationship(back_populates="snapshots")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("repositories.id"), index=True)
    repository: Mapped[Repository] = relationship(back_populates="runs")
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    baseline_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_baseline_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_target_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.QUEUED.value, index=True)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    runtime_info: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_runs_status_lease", "status", "locked_at"),
    )


class ChangedFile(Base):
    __tablename__ = "changed_files"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    old_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(String(32))
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supported: Mapped[bool] = mapped_column(Boolean, default=True)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_lines: Mapped[list] = mapped_column(JSON, default=list)
    removed_lines: Mapped[list] = mapped_column(JSON, default=list)
    coverage: Mapped[dict] = mapped_column(JSON, default=dict)
    scopes: Mapped[list["ChangedScope"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class ChangedScope(Base):
    __tablename__ = "changed_scopes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("changed_files.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    qualname: Mapped[str] = mapped_column(Text)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    changed_lines: Mapped[list] = mapped_column(JSON, default=list)
    executable_lines: Mapped[list] = mapped_column(JSON, default=list)
    covered_changed_lines: Mapped[list] = mapped_column(JSON, default=list)
    uncovered_changed_lines: Mapped[list] = mapped_column(JSON, default=list)
    coverage_status: Mapped[str] = mapped_column(String(32), default="COVERAGE_UNAVAILABLE")
    file: Mapped[ChangedFile] = relationship(back_populates="scopes")


class TestRecord(Base):
    __tablename__ = "test_records"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    baseline_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    modified_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_changed_lines: Mapped[dict] = mapped_column(JSON, default=dict)
    ran_changed_code: Mapped[bool] = mapped_column(Boolean, default=False)


class VerificationAttempt(Base):
    __tablename__ = "verification_attempts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    file_path: Mapped[str] = mapped_column(Text)
    function_qualname: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))
    classification: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    baseline_outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    modified_outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    property_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    reproducible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    minimized: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    environment: Mapped[dict] = mapped_column(JSON, default=dict)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    rel_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JobEvent(Base):
    __tablename__ = "job_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[str] = mapped_column(String(16), default="info")
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)