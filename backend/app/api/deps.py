import secrets
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Workspace
from app.db.session import get_session


@dataclass
class _Bucket:
    hits: list[float] = field(default_factory=list)


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self.lock = threading.Lock()
        self.buckets: dict[str, _Bucket] = defaultdict(_Bucket)
        self.last_prune = time.time()

    def check(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            if now - self.last_prune > 300:
                self.buckets = defaultdict(_Bucket)
                self.last_prune = now
            bucket = self.buckets[key]
            bucket.hits = [t for t in bucket.hits if now - t < 60]
            if len(bucket.hits) >= self.per_minute:
                return False
            bucket.hits.append(now)
            return True


_rate_limiter = RateLimiter(settings.rate_limit_per_minute)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    if not _rate_limiter.check(client_key(request)):
        raise HTTPException(status_code=429, detail="rate limit exceeded")


def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    configured = settings.api_key
    if not configured:
        return
    supplied = None
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    elif x_api_key:
        supplied = x_api_key.strip()
    if supplied is None or not secrets.compare_digest(supplied, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="valid API key required")


def get_db() -> Generator[Session, None, None]:
    gen = get_session()
    db = next(gen)
    try:
        yield db
    finally:
        gen.close()


DbDep = Depends(get_db)
RateLimitDep = Depends(enforce_rate_limit)


def get_workspace(db: Session) -> Workspace:
    ws = db.query(Workspace).filter(Workspace.name == "default").first()
    if ws is None:
        ws = Workspace(name="default")
        db.add(ws)
        db.commit()
    return ws


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]
