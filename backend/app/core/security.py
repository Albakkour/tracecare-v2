"""Optional shared demo-password gate and per-client rate limiting.

Both work on serverless platforms (Vercel): session tokens are signed with SESSION_SECRET (shared by all
instances) and rate-limit hits are stored in the database. Client IPs are stored only as salted hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request
from sqlalchemy import delete, func, select

from app.core.config import get_settings

logger = logging.getLogger("tracecare.security")
SESSION_TTL_SECONDS = 8 * 3600
_FALLBACK_KEY = secrets.token_bytes(32)  # local development only (no SESSION_SECRET set)


def _key() -> bytes:
    secret = get_settings().session_secret
    return secret.encode() if secret else _FALLBACK_KEY


def _sign(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(_key(), payload, hashlib.sha256).digest()).decode().rstrip("=")


def issue_session_token() -> tuple[str, int]:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = str(expires).encode()
    return f"{payload.decode()}.{_sign(payload)}", expires


def verify_session_token(token: str) -> bool:
    try:
        expires_s, sig = token.split(".", 1)
        if int(expires_s) < time.time():
            return False
        return hmac.compare_digest(sig, _sign(expires_s.encode()))
    except (ValueError, AttributeError):
        return False


def check_password(password: str) -> bool:
    expected = get_settings().demo_access_password
    return bool(expected) and hmac.compare_digest(password.encode(), expected.encode())


def require_demo_access(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: enforced only when DEMO_ACCESS_PASSWORD is set."""
    if not get_settings().demo_access_password:
        return
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not verify_session_token(token):
        raise HTTPException(status_code=401, detail="Demo access password required.")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hashed_client_key(scope: str, ip: str) -> str:
    digest = hmac.new(_key(), f"{scope}:{ip}".encode(), hashlib.sha256).hexdigest()
    return f"{scope}:{digest[:40]}"


class RateLimiter:
    """Sliding-window limiter stored in the database, with an in-memory fallback if the DB is down."""

    def __init__(self) -> None:
        self._memory: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, scope: str, ip: str) -> None:
        limit = get_settings().rate_limit()
        if limit is None:
            return
        max_requests, window = limit
        key = hashed_client_key(scope, ip)
        now = time.time()
        try:
            count = self._check_db(key, now, window)
        except HTTPException:
            raise
        except Exception as exc:  # database unavailable: degrade to per-instance limiting
            logger.warning("rate limiter falling back to memory: %s", type(exc).__name__)
            count = self._check_memory(key, now, window)
        if count > max_requests:
            raise HTTPException(status_code=429, detail=f"Rate limit reached ({max_requests} per "
                                                        f"{window // 60 or 1} min). Please try again later.",
                                headers={"Retry-After": str(window)})

    def _check_db(self, key: str, now: float, window: int) -> int:
        from app.storage.database import RateLimitHit, get_sessionmaker

        with get_sessionmaker()() as session:
            session.execute(delete(RateLimitHit).where(RateLimitHit.created_at < now - window))
            session.add(RateLimitHit(key=key, created_at=now))
            session.flush()
            count = session.scalar(select(func.count()).select_from(RateLimitHit).where(RateLimitHit.key == key))
            session.commit()
            return int(count or 0)

    def _check_memory(self, key: str, now: float, window: int) -> int:
        with self._lock:
            hits = self._memory[key]
            while hits and now - hits[0] > window:
                hits.popleft()
            hits.append(now)
            return len(hits)

    def reset(self) -> None:
        with self._lock:
            self._memory.clear()
        try:
            from app.storage.database import RateLimitHit, get_sessionmaker

            with get_sessionmaker()() as session:
                session.execute(delete(RateLimitHit))
                session.commit()
        except Exception:
            pass


analysis_rate_limiter = RateLimiter()
