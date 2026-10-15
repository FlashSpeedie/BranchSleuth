from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    git_url: str | None = Field(default=None, max_length=2048)
    local_path: str | None = Field(default=None, max_length=1024)
    default_branch: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        return v


class SnapshotInfo(BaseModel):
    id: uuid.UUID
    label: str
    file_count: int
    created_at: datetime


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    source_type: str
    url: str | None = None
    local_path: str | None = None
    default_branch: str | None = None
    created_at: datetime
    updated_at: datetime
    snapshot_count: int = 0


class RepositoryListOut(BaseModel):
    items: list[RepositoryOut]
    total: int


class RefOut(BaseModel):
    name: str
    sha: str


class AnalysisOptions(BaseModel):
    run_baseline_tests: bool = True
    run_modified_tests: bool = True
    collect_coverage: bool = True
    targeted_verification: bool = True
    hypothesis_max_examples: int = Field(default=60, ge=1, le=500)
    hypothesis_deadline_ms: int = Field(default=2000, ge=50, le=60000)
    property_code: str | None = Field(default=None, max_length=8000)
    property_target: str | None = Field(default=None, max_length=1024, description="file.py::qualname for the property")


class AnalysisCreate(BaseModel):
    repository_id: uuid.UUID
    baseline_ref: str | None = Field(default=None, max_length=255)
    target_ref: str | None = Field(default=None, max_length=255)
    options: AnalysisOptions = AnalysisOptions()


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    repository_id: uuid.UUID
    baseline_ref: str | None
    target_ref: str | None
    resolved_baseline_sha: str | None
    resolved_target_sha: str | None
    status: str
    stage: str | None
    stage_detail: str | None
    error_message: str | None
    attempts: int
    options: dict
    summary: dict
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    repository_name: str | None = None


class AnalysisListOut(BaseModel):
    items: list[AnalysisOut]
    total: int


class ScopeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    name: str
    qualname: str
    start_line: int
    end_line: int
    changed_lines: list
    executable_lines: list
    covered_changed_lines: list
    uncovered_changed_lines: list
    coverage_status: str


class ChangedFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    path: str
    old_path: str | None
    change_type: str
    language: str | None
    supported: bool
    parse_error: str | None
    added_lines: list
    removed_lines: list
    coverage: dict
    scopes: list[ScopeOut] = []


class TestRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    node_id: str
    name: str
    baseline_outcome: str | None
    modified_outcome: str | None
    category: str
    duration_ms: float | None
    error_excerpt: str | None
    executed_changed_lines: dict
    ran_changed_code: bool


class VerificationAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    scope_id: uuid.UUID | None
    file_path: str
    function_qualname: str
    kind: str
    classification: str
    rationale: str | None
    input_payload: dict | None
    baseline_outcome: dict | None
    modified_outcome: dict | None
    property_code: str | None
    reproducible: bool | None
    minimized: bool
    duration_ms: float | None
    environment: dict
    detail: dict


class JobEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ts: datetime
    level: str
    stage: str | None
    message: str
    detail: dict


class GraphNode(BaseModel):
    id: str
    type: str
    label: str
    data: dict


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    data: dict


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool


class HealthOut(BaseModel):
    status: str
    version: str
    database: str
    docker: str
    detail: dict


class ErrorOut(BaseModel):
    error: str
    detail: str | None = None
