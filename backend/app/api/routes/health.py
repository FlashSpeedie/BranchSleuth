from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbDep
from app.config import settings
from app.schemas.schemas import HealthOut

router = APIRouter()


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        status="ok",
        version="1.0.0",
        database="unchecked",
        docker="unchecked",
        detail={"service": "branchsleuth-api"},
    )


@router.get("/ready", response_model=HealthOut)
def ready(db=DbDep) -> HealthOut:
    database = "unknown"
    try:
        db.execute(text("SELECT 1"))
        database = "connected"
    except Exception as e:
        database = f"error:{type(e).__name__}"
    docker = "unconfigured"
    detail: dict = {"service": "branchsleuth-api", "local_repos": settings.allow_local_repos}
    try:
        from app.worker_runtime.docker_worker import get_docker_client

        client = get_docker_client()
        docker = "available"
        try:
            client.images.get(settings.worker_image)
            detail["worker_image"] = "built"
        except Exception:
            detail["worker_image"] = "not_built"
        client.close()
    except Exception as e:
        docker = "unavailable"
        detail["docker_reason"] = str(e)[:200]
    overall = "ok" if database == "connected" else "degraded"
    return HealthOut(status=overall, version="1.0.0", database=database, docker=docker, detail=detail)
