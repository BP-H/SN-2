import logging
import os
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Optional

from fastapi import Request


RATE_LIMIT_LOGGER = logging.getLogger("supernova.rate_limits")
RATE_LIMIT_BUCKET_CONFIG: Dict[str, Dict[str, int | str]] = {
    "auth": {"env": "SUPERNOVA_RATE_LIMIT_AUTH_PER_MINUTE", "default": 24, "window": 60},
    "uploads": {"env": "SUPERNOVA_RATE_LIMIT_UPLOADS_PER_HOUR", "default": 80, "window": 3600},
    "ai_generation": {"env": "SUPERNOVA_RATE_LIMIT_AI_GENERATION_PER_MINUTE", "default": 36, "window": 60},
    "writes": {"env": "SUPERNOVA_RATE_LIMIT_WRITES_PER_MINUTE", "default": 180, "window": 60},
    "messages": {"env": "SUPERNOVA_RATE_LIMIT_MESSAGES_PER_MINUTE", "default": 120, "window": 60},
    "public_reads": {"env": "SUPERNOVA_RATE_LIMIT_PUBLIC_READS_PER_MINUTE", "default": 1200, "window": 60},
}
RATE_LIMIT_FRIENDLY_DETAIL = (
    "Slow down for a moment so the commons stays reachable. "
    "This protects the network from spam and runaway automation."
)
_RATE_LIMIT_WINDOWS: Dict[str, deque[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def _env_int_at_least(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def _rate_limit_enabled() -> bool:
    return _env_bool("SUPERNOVA_RATE_LIMIT_ENABLED", True)


def _rate_limit_path_bucket(method: str, path: str) -> Optional[str]:
    clean_path = "/" + str(path or "").lstrip("/")
    clean_method = str(method or "").upper()
    if clean_method in {"OPTIONS", "HEAD"}:
        return None
    if clean_path in {"/health", "/supernova-status", "/status"}:
        return None
    if clean_path.startswith(("/.well-known/", "/protocol", "/core")):
        return None
    if clean_method == "GET" and clean_path.startswith("/uploads/"):
        return None
    if clean_method == "POST" and (
        clean_path.startswith("/auth/")
        or clean_path in {"/users/register", "/login", "/register", "/token"}
    ):
        return "auth"
    if clean_method in {"POST", "PUT", "PATCH"} and (
        clean_path.startswith("/upload-") or clean_path.startswith("/uploads")
    ):
        return "uploads"
    if clean_method == "POST" and (
        "/draft-ai-" in clean_path
        or clean_path == "/ai/delegates/persona-draft"
        or clean_path == "/connector/actions/draft-ai-review"
    ):
        return "ai_generation"
    if clean_path.startswith("/messages"):
        return "messages" if clean_method in {"POST", "PUT", "PATCH", "DELETE"} else "public_reads"
    if clean_method in {"POST", "PUT", "PATCH", "DELETE"}:
        return "writes"
    if clean_method == "GET":
        return "public_reads"
    return None


def _rate_limit_config(bucket: str) -> tuple[int, int]:
    config = RATE_LIMIT_BUCKET_CONFIG.get(bucket) or RATE_LIMIT_BUCKET_CONFIG["writes"]
    limit = _env_int_at_least(str(config["env"]), int(config["default"]), 1)
    return limit, int(config["window"])


def _rate_limit_identity(
    request: Request,
    *,
    jwt_module: Any = None,
    settings_getter: Optional[Callable[[], Any]] = None,
) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    host = forwarded or getattr(request.client, "host", "") or "unknown"
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer ") and jwt_module is not None and settings_getter is not None:
        token = authorization.split(" ", 1)[1].strip()
        try:
            settings = settings_getter()
            claims = jwt_module.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id = claims.get("uid")
            subject = str(claims.get("sub") or "").strip().lower()
            if user_id is not None:
                return f"user:{int(user_id)}"
            if subject:
                return f"user:{subject}"
        except Exception:
            pass
    return f"ip:{host}"


def _rate_limit_identity_type(identity: str) -> str:
    return "user" if str(identity or "").startswith("user:") else "ip"


def rate_limit_attempt(
    request: Request,
    *,
    jwt_module: Any = None,
    settings_getter: Optional[Callable[[], Any]] = None,
) -> tuple[Optional[str], Optional[int]]:
    if not _rate_limit_enabled():
        return None, None
    bucket = _rate_limit_path_bucket(request.method, request.url.path)
    if not bucket:
        return None, None
    limit, window_seconds = _rate_limit_config(bucket)
    now = time.monotonic()
    identity = _rate_limit_identity(request, jwt_module=jwt_module, settings_getter=settings_getter)
    key = f"{bucket}:{identity}"
    with _RATE_LIMIT_LOCK:
        attempts = _RATE_LIMIT_WINDOWS.setdefault(key, deque())
        cutoff = now - window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= limit:
            retry_after = max(1, int(window_seconds - (now - attempts[0])) + 1)
            identity_type = _rate_limit_identity_type(identity)
            RATE_LIMIT_LOGGER.info(
                "rate_limit_exceeded bucket=%s identity_type=%s retry_after=%s limit=%s window_seconds=%s",
                bucket,
                identity_type,
                retry_after,
                limit,
                window_seconds,
                extra={
                    "supernova_rate_limit_bucket": bucket,
                    "supernova_rate_limit_identity_type": identity_type,
                    "supernova_rate_limit_retry_after": retry_after,
                    "supernova_rate_limit_limit": limit,
                    "supernova_rate_limit_window_seconds": window_seconds,
                },
            )
            return bucket, retry_after
        attempts.append(now)
    return bucket, None


def _reset_rate_limit_state_for_tests() -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_WINDOWS.clear()
