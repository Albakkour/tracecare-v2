"""SQLAlchemy engine/session. SQLite locally, Supabase PostgreSQL when DATABASE_URL points there."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


class Encounter(Base):
    """Mirrors supabase/migrations/001_initial_schema.sql."""

    __tablename__ = "encounters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    language: Mapped[str] = mapped_column(String(16), default="en")
    template_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(32))
    # Raw transcript is not stored; the analysis result keeps the parsed segments needed for evidence.
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_result: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    review_status: Mapped[str] = mapped_column(String(32), default="provisional_review_required")


class RateLimitHit(Base):
    """One row per rate-limited request. `key` is a salted hash, never a raw IP address."""

    __tablename__ = "rate_limit_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        url = settings.sqlalchemy_database_url
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # prepare_threshold=None disables server-side prepared statements, which keeps psycopg
            # compatible with PgBouncer/Supavisor transaction pooling (Supabase port 6543).
            kwargs["connect_args"] = {"prepare_threshold": None, "connect_timeout": 10}
            if settings.is_serverless:
                kwargs["poolclass"] = NullPool  # short-lived function instances: no idle pool
            else:
                kwargs.update(pool_size=5, max_overflow=5, pool_recycle=300)
        engine = create_engine(url, **kwargs)
        # Create tables on first use (idempotent). Does not rely on the app's startup hook, which may not
        # run before the first request on serverless platforms.
        Base.metadata.create_all(engine)
        _engine = engine
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> sessionmaker:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def check_db() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_engine() -> None:
    """Used by tests to point at a fresh database."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
