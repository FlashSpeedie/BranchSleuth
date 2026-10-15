from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine = None
_session_factory: sessionmaker | None = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(
            settings.sqlalchemy_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=1800,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def make_session_factory(url: str):
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_session() -> Generator[Session, None, None]:
    get_engine()
    assert _session_factory is not None
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()
