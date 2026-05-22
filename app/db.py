from collections.abc import Generator

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, future=True, **_engine_args(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def is_database_operational() -> bool:
    return not settings.requires_persistent_database


def require_operational_database() -> None:
    if not is_database_operational():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL must be configured with a Postgres/Neon connection string on Vercel before lead data endpoints can run.",
        )


def init_db() -> None:
    if not is_database_operational():
        return

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    require_operational_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
