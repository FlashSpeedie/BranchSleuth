from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore", env_prefix="BS_")

    database_url: str = ""
    api_key: str = ""
    allowed_git_hosts: str = "github.com,gitlab.com,bitbucket.org"
    data_dir: str = "./data"
    allow_local_repos: bool = False
    max_upload_bytes: int = 52_428_800
    max_extracted_bytes: int = 209_715_200
    max_repo_files: int = 20_000
    container_mem_bytes: int = 2_147_483_648
    container_cpus: float = 2.0
    deps_timeout_seconds: int = 300
    tests_timeout_seconds: int = 600
    probe_timeout_seconds: int = 240
    hypothesis_max_examples: int = 60
    hypothesis_deadline_ms: int = 2000
    cors_origins: str = "http://localhost:3000"
    ai_gateway_url: str = ""
    ai_gateway_key: str = ""
    worker_image: str = "branchsleuth/worker:py312-1"
    worker_base_image: str = "python:3.12-slim"
    job_lease_seconds: int = 900
    max_job_attempts: int = 3
    rate_limit_per_minute: int = 120

    @property
    def allowed_host_set(self) -> set[str]:
        return {h.strip().lower() for h in self.allowed_git_hosts.split(",") if h.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def sqlalchemy_url(self) -> str:
        url = self.database_url.strip()
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        elif url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        if "sslmode" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        return url

    def data_path(self) -> Path:
        p = Path(self.data_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
