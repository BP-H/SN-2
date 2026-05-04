import base64
import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import urllib.request
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import and_, asc, desc, func, or_, text
from sqlalchemy.orm import Session

try:
    from jose import JWTError, jwt
except Exception:  # pragma: no cover - optional dependency during partial environments
    JWTError = Exception
    jwt = None

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
SUPER_NOVA_DIR = BACKEND_DIR / 'supernova_2177_ui_weighted'
PROTOCOL_DIR_CANDIDATES = (PROJECT_DIR / "protocol", BACKEND_DIR / "protocol")
PROTOCOL_DIR = next((path for path in PROTOCOL_DIR_CANDIDATES if path.exists()), PROTOCOL_DIR_CANDIDATES[0])

for path in (BACKEND_DIR, SUPER_NOVA_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

try:
    from .supernova_runtime import load_supernova_runtime, runtime_status
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from supernova_runtime import load_supernova_runtime, runtime_status


def _load_supernova_runtime():
    runtime = load_supernova_runtime()
    if not runtime.get('available'):
        exc = runtime.get('error')
        print(f'Warning: falling back to standalone backend mode: {exc}')
    return runtime

try:
    import auth_utils
except Exception:  # pragma: no cover - auth helpers may be unavailable in partial environments
    auth_utils = None

try:
    from .commons_rate_limits import RATE_LIMIT_FRIENDLY_DETAIL, rate_limit_attempt
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from commons_rate_limits import RATE_LIMIT_FRIENDLY_DETAIL, rate_limit_attempt

try:
    from .status_routes import build_supernova_runtime_payload, create_status_router
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from status_routes import build_supernova_runtime_payload, create_status_router

try:
    from .routers.messages import create_messages_router
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from routers.messages import create_messages_router

try:
    from .routers.uploads import create_uploads_router
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from routers.uploads import create_uploads_router

try:
    from .routers.social_graph import create_social_graph_router
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from routers.social_graph import create_social_graph_router

try:
    from .routers.ai_delegates import create_ai_delegates_router
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from routers.ai_delegates import create_ai_delegates_router

try:
    from .routers.ai_readonly import create_ai_readonly_router
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from routers.ai_readonly import create_ai_readonly_router


_runtime = _load_supernova_runtime()
SUPER_NOVA_AVAILABLE = _runtime['available']
SUPER_NOVA_STATUS = runtime_status(_runtime)
SUPER_NOVA_ERROR = _runtime.get('error')
SUPER_NOVA_CORE_APP = _runtime.get('core_app')
SUPER_NOVA_CORE_ROUTES = _runtime.get('core_routes') or []
DELETED_COMMENT_TEXT = "[deleted]"
LEGACY_SHA256_LENGTH = 64
PBKDF2_HASH_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = int(os.environ.get("PASSWORD_PBKDF2_ITERATIONS", "260000"))


def _env_int_at_least(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


WRAPPER_ACCESS_TOKEN_MINUTES = _env_int_at_least("SUPERNOVA_ACCESS_TOKEN_MINUTES", 720, 15)
SYSTEM_VOTE_QUESTION = os.environ.get(
    "SYSTEM_VOTE_QUESTION",
    "Should SuperNova prioritize AI rights as the next major research focus?",
)
SYSTEM_VOTE_DEADLINE = (os.environ.get("SYSTEM_VOTE_DEADLINE") or "").strip() or None
PUBLIC_BASE_URL = (
    os.environ.get("SUPERNOVA_PUBLIC_URL")
    or os.environ.get("PUBLIC_BASE_URL")
    or os.environ.get("NEXT_PUBLIC_SITE_URL")
    or "https://2177.tech"
).rstrip("/")
PRODUCTION_ENVIRONMENT_NAMES = (
    "SUPERNOVA_ENV",
    "APP_ENV",
    "ENV",
    "RAILWAY_ENVIRONMENT",
)
PRODUCTION_ENVIRONMENT_VALUES = {"production", "prod"}
WEAK_SECRET_KEY_VALUES = {"", "changeme", "dev", "secret", "default"}


def _is_explicit_production_environment(environ: Optional[Dict[str, str]] = None) -> bool:
    source = os.environ if environ is None else environ
    return any(
        str(source.get(name, "")).strip().lower() in PRODUCTION_ENVIRONMENT_VALUES
        for name in PRODUCTION_ENVIRONMENT_NAMES
    )


def _is_weak_secret_key(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in WEAK_SECRET_KEY_VALUES


def _fallback_secret_key_from_env(environ: Optional[Dict[str, str]] = None) -> str:
    source = os.environ if environ is None else environ
    secret_key = source.get("SECRET_KEY")
    if _is_explicit_production_environment(source) and _is_weak_secret_key(secret_key):
        raise RuntimeError("SECRET_KEY must be set to a non-placeholder value in production.")
    return secret_key or "changeme"


def _parse_allowed_origins() -> Dict[str, Any]:
    raw = os.environ.get("ALLOWED_ORIGINS") or os.environ.get("BACKEND_ALLOWED_ORIGINS") or ""
    origins = [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]
    if not origins:
        return {
            "origins": ["*"],
            "mode": "open_federation_default",
            "public_api_cors_open": True,
            "warning": "",
            "note": "Public non-cookie API access is open by design; identity is protected by tokens and server-side checks.",
        }
    if "*" in origins:
        return {
            "origins": ["*"],
            "mode": "open_federation_env",
            "public_api_cors_open": True,
            "warning": "",
            "note": "Wildcard CORS is explicitly configured for open federation; credentials remain disabled.",
        }
    return {
        "origins": origins,
        "mode": "allowlist",
        "public_api_cors_open": False,
        "warning": "",
        "note": "CORS is allowlisted by environment configuration. Use this only when intentionally running a private surface.",
    }


CORS_CONFIG = _parse_allowed_origins()
PUBLIC_FEDERATION_CACHE_HEADERS = {"Cache-Control": "public, max-age=300"}
NO_STORE_PREFIXES = (
    "/auth",
    "/messages",
    "/follows",
    "/api/ai",
    "/users/me",
    "/upload-image",
)
SUPERNOVA_INSTANCE_VERSION = "2026-04"

if SUPER_NOVA_AVAILABLE:
    SessionLocal = _runtime['session_local']
    get_db = _runtime['get_db']
    get_settings = _runtime['get_settings']
    weighted_decide = _runtime['weighted_decide']
    get_weighted_threshold = _runtime['get_weighted_threshold']
    tally_votes = _runtime['tally_votes']
    DB_ENGINE_URL = _runtime['db_engine_url']
    Proposal = _runtime['models']['Proposal']
    ProposalVote = _runtime['models']['ProposalVote']
    Comment = _runtime['models']['Comment']
    Decision = _runtime['models']['Decision']
    Run = _runtime['models']['Run']
    Harmonizer = _runtime['models']['Harmonizer']
    VibeNode = _runtime['models']['VibeNode']
    SystemState = _runtime['models']['SystemState']
else:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///./supernova_local.db')
    engine = create_engine(
        DATABASE_URL,
        future=True,
        connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    DB_ENGINE_URL = DATABASE_URL

    try:
        from db_models import (
            Base as SharedBase,
            Comment,
            Decision,
            Harmonizer,
            Proposal,
            ProposalVote,
            Run,
            SystemState,
            VibeNode,
        )

        SharedBase.metadata.create_all(bind=engine)
    except Exception as exc:
        print(f"Warning: could not initialize standalone database schema: {exc}")
        Proposal = ProposalVote = Comment = Decision = Run = Harmonizer = VibeNode = SystemState = None

    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def weighted_decide(*_args, **_kwargs):
        return {'status': 'undecided', 'note': 'standalone mode'}

    def tally_votes(*_args, **_kwargs):
        return {'up': 0, 'down': 0, 'total': 0}

    def get_weighted_threshold(level: str = 'standard'):
        return 0.9 if str(level).lower() == 'important' else 0.6

    def get_settings():
        class Settings:
            DB_MODE = 'standalone'
            UNIVERSE_ID = 'standalone'
            SECRET_KEY = _fallback_secret_key_from_env()
            ALGORITHM = os.environ.get('ALGORITHM', 'HS256')

            @property
            def engine_url(self):
                return DB_ENGINE_URL

        return Settings()

try:
    from db_models import Notification
except Exception:  # pragma: no cover - optional in partial backend environments
    Notification = None

try:
    from db_models import ProposalCollab
except Exception:  # pragma: no cover - optional before collab model support
    ProposalCollab = None

try:
    from db_models import ConnectorActionProposal
except Exception:  # pragma: no cover - optional before connector action model support
    ConnectorActionProposal = None

try:
    from mention_parser import parse_mentions
except Exception:  # pragma: no cover - parser is optional in partial environments
    parse_mentions = None


CRUD_MODELS_AVAILABLE = all(
    model is not None for model in (Proposal, ProposalVote, Comment, Harmonizer, VibeNode)
)


def _is_legacy_sha256_hash(value: str) -> bool:
    candidate = (value or "").strip().lower()
    return len(candidate) == LEGACY_SHA256_LENGTH and all(char in "0123456789abcdef" for char in candidate)


def _b64encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode_bytes(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _hash_password_pbkdf2(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_HASH_PREFIX}${PBKDF2_ITERATIONS}${_b64encode_bytes(salt)}${_b64encode_bytes(digest)}"


def _verify_password_pbkdf2(password: str, hashed_password: str) -> bool:
    try:
        prefix, iterations, salt, digest = (hashed_password or "").split("$", 3)
        if prefix != PBKDF2_HASH_PREFIX:
            return False
        iteration_count = int(iterations)
        expected = _b64decode_bytes(digest)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64decode_bytes(salt),
            iteration_count,
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _hash_password_strict(password: str) -> str:
    """Create new password hashes without falling back to unsalted SHA-256."""
    if auth_utils and hasattr(auth_utils, "pwd_context"):
        try:
            return auth_utils.pwd_context.hash(password)
        except Exception:
            pass
    return _hash_password_pbkdf2(password)


def _verify_password_with_legacy_upgrade(password: str, hashed_password: str) -> tuple[bool, bool]:
    stored_hash = (hashed_password or "").strip()
    if not stored_hash:
        return False, False
    if stored_hash.startswith(f"{PBKDF2_HASH_PREFIX}$"):
        return _verify_password_pbkdf2(password, stored_hash), False
    if _is_legacy_sha256_hash(stored_hash):
        return hashlib.sha256(password.encode()).hexdigest() == stored_hash.lower(), True
    if not auth_utils or not hasattr(auth_utils, "pwd_context"):
        return False, False
    try:
        return bool(auth_utils.pwd_context.verify(password, stored_hash)), False
    except Exception:
        return False, False
WORKFLOW_MODELS_AVAILABLE = all(
    model is not None for model in (Decision, Run)
)


def persist_weighted_vote_record(
    proposal_id: int, voter: str, choice: str, species: str = 'human'
):
    if ProposalVote is None:
        return {'ok': True, 'note': 'standalone mode'}

    try:
        session = SessionLocal()
        vote_entry = ProposalVote(
            proposal_id=proposal_id,
            harmonizer_id=voter,
            vote=choice,
            voter_type=species,
        )
        session.add(vote_entry)
        session.commit()
        return {'ok': True, 'proposal_id': proposal_id, 'voter': voter, 'choice': choice}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    finally:
        if 'session' in locals():
            session.close()

# --- FastAPI setup ---
app = FastAPI(
    title="SuperNova 2177 API",
    description="Backend API for SuperNova 2177 - Unified Version",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_CONFIG["origins"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def cache_control_middleware(request: Request, call_next):
    response = await call_next(request)
    if "cache-control" in response.headers:
        return response
    path = request.url.path
    if request.method not in {"GET", "HEAD"} or any(path.startswith(prefix) for prefix in NO_STORE_PREFIXES):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def commons_rate_limit_middleware(request: Request, call_next):
    bucket, retry_after = rate_limit_attempt(request, jwt_module=jwt, settings_getter=get_settings)
    if retry_after is not None:
        return JSONResponse(
            status_code=429,
            content={
                "detail": RATE_LIMIT_FRIENDLY_DETAIL,
                "error_code": "rate_limited",
                "bucket": bucket,
                "retry_after_seconds": retry_after,
            },
            headers={
                "Retry-After": str(retry_after),
                "X-SuperNova-RateLimit-Bucket": bucket or "unknown",
            },
        )
    response = await call_next(request)
    if bucket:
        response.headers["X-SuperNova-RateLimit-Bucket"] = bucket
    return response


uploads_dir = os.environ.get("UPLOADS_DIR") or os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")
if PROTOCOL_DIR.exists():
    app.mount("/protocol", StaticFiles(directory=str(PROTOCOL_DIR)), name="protocol")
if SUPER_NOVA_CORE_APP is not None:
    app.mount("/core", SUPER_NOVA_CORE_APP, name="supernova_core")

IMAGE_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp", ".heic", ".heif"}
VIDEO_UPLOAD_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".ogg", ".ogv"}
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/ogg": ".ogv",
    "application/pdf": ".pdf",
    "application/json": ".json",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/csv": ".csv",
    "text/markdown": ".md",
    "text/plain": ".txt",
}
GENERIC_UPLOAD_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
DOCUMENT_UPLOAD_EXTENSIONS = {
    ".csv",
    ".doc",
    ".docx",
    ".json",
    ".md",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".txt",
    ".xls",
    ".xlsx",
}


def _upload_limit_from_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


UPLOAD_IMAGE_MAX_BYTES = _upload_limit_from_env("UPLOAD_IMAGE_MAX_BYTES", 20 * 1024 * 1024)
UPLOAD_AVATAR_MAX_BYTES = _upload_limit_from_env("UPLOAD_AVATAR_MAX_BYTES", UPLOAD_IMAGE_MAX_BYTES)
UPLOAD_VIDEO_MAX_BYTES = _upload_limit_from_env("UPLOAD_VIDEO_MAX_BYTES", 250 * 1024 * 1024)
UPLOAD_DOCUMENT_MAX_BYTES = _upload_limit_from_env("UPLOAD_DOCUMENT_MAX_BYTES", 50 * 1024 * 1024)
UPLOAD_COPY_CHUNK_BYTES = 1024 * 1024


def _safe_upload_extension(upload: UploadFile, fallback: str = "") -> str:
    raw_ext = os.path.splitext(upload.filename or "")[1].lower()
    if raw_ext and 1 < len(raw_ext) <= 12 and raw_ext[1:].replace("-", "").isalnum():
        return raw_ext
    return CONTENT_TYPE_EXTENSIONS.get((upload.content_type or "").lower(), fallback)


def _upload_matches(upload: UploadFile, prefix: str, allowed_extensions: set[str]) -> bool:
    content_type = (upload.content_type or "").lower()
    if content_type.startswith(prefix):
        return True
    return content_type in GENERIC_UPLOAD_TYPES and _safe_upload_extension(upload) in allowed_extensions


def _remove_partial_upload(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _copy_upload_file_bounded(upload: UploadFile, file_path: str, max_bytes: int) -> None:
    written = 0
    try:
        upload.file.seek(0)
    except Exception:
        pass
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = upload.file.read(UPLOAD_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(status_code=413, detail="Uploaded file is too large")
                f.write(chunk)
    except Exception:
        _remove_partial_upload(file_path)
        raise


def _save_upload_file(
    upload: UploadFile,
    allowed_extensions: Optional[set[str]] = None,
    fallback_ext: str = "",
    max_bytes: int = UPLOAD_DOCUMENT_MAX_BYTES,
) -> str:
    ext = _safe_upload_extension(upload, fallback_ext)
    if allowed_extensions is not None and ext not in allowed_extensions:
        ext = fallback_ext if fallback_ext in allowed_extensions else ""
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(uploads_dir, unique_name)
    _copy_upload_file_bounded(upload, file_path, max_bytes)
    return unique_name


def _format_timestamp(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return ""
        try:
            return datetime.datetime.fromisoformat(normalized.replace("Z", "+00:00")).isoformat()
        except Exception:
            return normalized
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:
            pass
    return str(value)


def _find_harmonizer_by_username(db: Session, username: Optional[str]):
    clean_username = (username or "").strip()
    if not clean_username or not CRUD_MODELS_AVAILABLE or Harmonizer is None:
        return None
    try:
        return (
            db.query(Harmonizer)
            .filter(func.lower(Harmonizer.username) == clean_username.lower())
            .first()
        )
    except Exception:
        return None


def _ensure_comment_votes_table(db: Session) -> None:
    try:
        id_column = "INTEGER PRIMARY KEY AUTOINCREMENT" if str(DB_ENGINE_URL or "").startswith("sqlite") else "SERIAL PRIMARY KEY"
        db.execute(text(f"""
            CREATE TABLE IF NOT EXISTS comment_votes (
                id {id_column},
                comment_id INTEGER NOT NULL,
                harmonizer_id INTEGER NOT NULL,
                voter TEXT,
                voter_type TEXT DEFAULT 'human',
                vote TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(comment_id, harmonizer_id)
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_comment_votes_comment_vote ON comment_votes (comment_id, vote)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS idx_comment_votes_harmonizer ON comment_votes (harmonizer_id)"))
        db.commit()
    except Exception:
        db.rollback()


def _comment_vote_summary(db: Session, comment_id: Optional[int]) -> Dict[str, Any]:
    if not comment_id:
        return {"likes": [], "dislikes": [], "total": 0}
    try:
        _ensure_comment_votes_table(db)
        rows = db.execute(
            text("SELECT voter, voter_type, vote FROM comment_votes WHERE comment_id = :comment_id ORDER BY id ASC"),
            {"comment_id": int(comment_id)},
        ).fetchall()
    except Exception:
        db.rollback()
        return {"likes": [], "dislikes": [], "total": 0}

    likes: List[Dict[str, str]] = []
    dislikes: List[Dict[str, str]] = []
    for row in rows:
        data = getattr(row, "_mapping", row)
        entry = {"voter": data["voter"], "type": data["voter_type"] or "human"}
        if data["vote"] == "up":
            likes.append(entry)
        elif data["vote"] == "down":
            dislikes.append(entry)
    return {"likes": likes, "dislikes": dislikes, "total": len(likes) + len(dislikes)}


def _serialize_comment_record(db: Session, comment) -> Dict:
    author_obj = None
    if CRUD_MODELS_AVAILABLE and getattr(comment, "author_id", None):
        author_obj = db.query(Harmonizer).filter(Harmonizer.id == comment.author_id).first()

    user_name = (
        getattr(author_obj, "username", None)
        or getattr(comment, "user", None)
        or "Anonymous"
    )
    if author_obj is None:
        author_obj = _find_harmonizer_by_username(db, user_name)
    user_img = (
        getattr(author_obj, "profile_pic", None)
        or getattr(comment, "user_img", None)
        or ""
    )
    species = (
        getattr(author_obj, "species", None)
        or getattr(comment, "species", None)
        or "human"
    )
    content = getattr(comment, "content", None) or getattr(comment, "comment", None) or ""
    deleted = str(content or "").strip() == DELETED_COMMENT_TEXT
    vote_summary = _comment_vote_summary(db, getattr(comment, "id", None))

    return {
        "id": getattr(comment, "id", None),
        "proposal_id": getattr(comment, "proposal_id", None),
        "parent_comment_id": getattr(comment, "parent_comment_id", None),
        "user": "[deleted]" if deleted else user_name,
        "user_img": "" if deleted or user_img == "default.jpg" else user_img,
        "species": "human" if deleted else species,
        "comment": "This comment was deleted." if deleted else content,
        "deleted": deleted,
        "likes": [] if deleted else vote_summary.get("likes", []),
        "dislikes": [] if deleted else vote_summary.get("dislikes", []),
        "created_at": _format_timestamp(getattr(comment, "created_at", None)),
    }


COMMENTS_READ_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_comments_proposal_created_id "
    "ON comments (proposal_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_comments_parent_created_id "
    "ON comments (parent_comment_id, created_at, id)",
)

DIRECT_MESSAGES_READ_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_direct_messages_conversation_created_id "
    "ON direct_messages (conversation_id, created_at, id)",
)

PROPOSAL_READ_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_proposals_created_id "
    "ON proposals (created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_proposal_votes_proposal_vote "
    "ON proposal_votes (proposal_id, vote)",
)


def _execute_index_statements(db: Session, statements: tuple[str, ...]) -> None:
    for statement in statements:
        db.execute(text(statement))


def _ensure_comments_read_indexes(db: Session) -> None:
    _execute_index_statements(db, COMMENTS_READ_INDEX_STATEMENTS)


def _ensure_direct_messages_read_indexes(db: Session) -> None:
    _execute_index_statements(db, DIRECT_MESSAGES_READ_INDEX_STATEMENTS)


def _ensure_proposal_read_indexes(db: Session) -> None:
    try:
        _execute_index_statements(db, PROPOSAL_READ_INDEX_STATEMENTS)
        db.commit()
    except Exception:
        db.rollback()


def _ensure_comment_thread_columns(db: Session) -> None:
    try:
        if str(DB_ENGINE_URL or "").startswith("sqlite"):
            columns = db.execute(text("PRAGMA table_info(comments)")).fetchall()
            column_names = {getattr(column, "_mapping", column)["name"] for column in columns}
            if "parent_comment_id" not in column_names:
                db.execute(text("ALTER TABLE comments ADD COLUMN parent_comment_id INTEGER"))
        else:
            db.execute(text("ALTER TABLE comments ADD COLUMN IF NOT EXISTS parent_comment_id INTEGER"))
        _ensure_comments_read_indexes(db)
        db.commit()
    except Exception:
        db.rollback()


def _is_deleted_comment_record(comment) -> bool:
    content = getattr(comment, "content", None) or getattr(comment, "comment", None) or ""
    return str(content or "").strip() == DELETED_COMMENT_TEXT


def _delete_comment_mention_links(db: Session, comment_ids: List[int]) -> None:
    clean_ids = []
    for comment_id in comment_ids or []:
        try:
            clean_ids.append(int(comment_id))
        except (TypeError, ValueError):
            continue
    if not clean_ids:
        return

    try:
        for comment_id in clean_ids:
            db.execute(
                text("DELETE FROM comment_mentions WHERE comment_id = :comment_id"),
                {"comment_id": comment_id},
            )
    except Exception as exc:
        db.rollback()
        message = str(exc).lower()
        table_missing = (
            "comment_mentions" in message
            and ("no such table" in message or "does not exist" in message or "undefinedtable" in message)
        )
        if not table_missing:
            raise


def _delete_comment_vote_links(db: Session, comment_ids: List[int]) -> None:
    clean_ids = []
    for comment_id in comment_ids or []:
        try:
            clean_ids.append(int(comment_id))
        except (TypeError, ValueError):
            continue
    if not clean_ids:
        return
    try:
        for comment_id in clean_ids:
            db.execute(
                text("DELETE FROM comment_votes WHERE comment_id = :comment_id"),
                {"comment_id": comment_id},
            )
    except Exception as exc:
        db.rollback()
        message = str(exc).lower()
        table_missing = (
            "comment_votes" in message
            and ("no such table" in message or "does not exist" in message or "undefinedtable" in message)
        )
        if not table_missing:
            raise


def _delete_proposal_collab_links(db: Session, proposal_ids: List[int]) -> None:
    clean_ids = []
    for proposal_id in proposal_ids or []:
        try:
            clean_ids.append(int(proposal_id))
        except (TypeError, ValueError):
            continue
    if not clean_ids:
        return

    try:
        if ProposalCollab is not None and CRUD_MODELS_AVAILABLE:
            db.query(ProposalCollab).filter(ProposalCollab.proposal_id.in_(clean_ids)).delete(
                synchronize_session=False
            )
            return
        for proposal_id in clean_ids:
            db.execute(
                text("DELETE FROM proposal_collabs WHERE proposal_id = :proposal_id"),
                {"proposal_id": proposal_id},
            )
    except Exception as exc:
        db.rollback()
        message = str(exc).lower()
        table_missing = (
            "proposal_collabs" in message
            and ("no such table" in message or "does not exist" in message or "undefinedtable" in message)
        )
        if not table_missing:
            raise


def _prune_empty_deleted_comment_ancestors(db: Session, parent_comment_id: Optional[int]) -> List[int]:
    pruned: List[int] = []
    current_parent_id = parent_comment_id
    while current_parent_id:
        if CRUD_MODELS_AVAILABLE:
            parent = db.query(Comment).filter(Comment.id == current_parent_id).first()
            if not parent or not _is_deleted_comment_record(parent):
                break
            child_count = db.query(Comment).filter(Comment.parent_comment_id == current_parent_id).count()
            if child_count:
                break
            next_parent_id = getattr(parent, "parent_comment_id", None)
            _delete_comment_mention_links(db, [current_parent_id])
            db.delete(parent)
            pruned.append(current_parent_id)
            current_parent_id = next_parent_id
            continue

        row = db.execute(
            text("SELECT * FROM comments WHERE id = :comment_id"),
            {"comment_id": current_parent_id},
        ).fetchone()
        if not row or not _is_deleted_comment_record(row):
            break
        child_count = db.execute(
            text("SELECT COUNT(*) FROM comments WHERE parent_comment_id = :comment_id"),
            {"comment_id": current_parent_id},
        ).scalar() or 0
        if child_count:
            break
        next_parent_id = getattr(row, "parent_comment_id", None)
        db.execute(text("DELETE FROM comments WHERE id = :comment_id"), {"comment_id": current_parent_id})
        pruned.append(current_parent_id)
        current_parent_id = next_parent_id
    return pruned


def _serialize_vote_record(db: Session, vote) -> tuple[Optional[Dict], Optional[Dict]]:
    voter_name = getattr(vote, "voter", None) or getattr(vote, "username", None)
    voter_type = getattr(vote, "voter_type", None) or getattr(vote, "species", None) or "human"

    if CRUD_MODELS_AVAILABLE and getattr(vote, "harmonizer_id", None):
        harmonizer_obj = db.query(Harmonizer).filter(Harmonizer.id == vote.harmonizer_id).first()
        if harmonizer_obj and hasattr(harmonizer_obj, "username"):
            voter_name = harmonizer_obj.username

    vote_field = getattr(vote, "vote", None)
    if vote_field is None:
        vote_field = getattr(vote, "choice", None)

    payload = {"voter": voter_name, "type": voter_type}
    if vote_field == "up":
        return payload, None
    if vote_field == "down":
        return None, payload
    return None, None


def _uploads_url(value: str) -> str:
    media = str(value or "").strip()
    if not media:
        return ""
    if media.startswith(("http://", "https://", "data:", "blob:", "/uploads/")):
        return media
    return f"/uploads/{media}"


def _absolute_public_media_url(value: str) -> str:
    media = _uploads_url(value)
    if not media:
        return ""
    if media.startswith(("http://", "https://", "data:image/")):
        return media
    if media.startswith("/"):
        return f"{PUBLIC_BASE_URL.rstrip('/')}{media}"
    return media


def _image_urls_from_storage(value) -> List[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    if isinstance(parsed, list):
        return [_uploads_url(item) for item in parsed if str(item or "").strip()]
    return [_uploads_url(raw)]


def _normalize_media_layout(value: Optional[str]) -> str:
    layout = str(value or "carousel").strip().lower()
    return "grid" if layout == "grid" else "carousel"


def _payload_dict(value) -> Dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value) if isinstance(value, str) else {}
    except Exception:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_governance_kind(value: Optional[str]) -> str:
    kind = str(value or "post").strip().lower()
    return "decision" if kind in {"decision", "proposal", "governance"} else "post"


def _normalize_decision_level(value: Optional[str]) -> str:
    level = str(value or "standard").strip().lower()
    return "important" if level == "important" else "standard"


def _clamp_voting_days(value, default: int = 3) -> int:
    try:
        days = int(value)
    except Exception:
        days = default
    return max(1, min(days, 30))


def _governance_threshold(level: str) -> float:
    try:
        threshold = float(get_weighted_threshold(level))
    except Exception:
        threshold = 0.9 if level == "important" else 0.6
    return threshold


def _proposal_governance_payload(payload: Dict, voting_deadline_value=None) -> Optional[Dict]:
    if _normalize_governance_kind(
        payload.get("governance_kind") or payload.get("proposal_kind") or payload.get("kind")
    ) != "decision":
        return None
    level = _normalize_decision_level(payload.get("decision_level"))
    threshold = payload.get("approval_threshold")
    try:
        threshold = float(threshold)
    except Exception:
        threshold = _governance_threshold(level)
    deadline = voting_deadline_value or payload.get("voting_deadline")
    return {
        "kind": "decision",
        "decision_level": level,
        "approval_threshold": threshold,
        "threshold": threshold,
        "voting_days": _clamp_voting_days(payload.get("voting_days")),
        "voting_deadline": _format_timestamp(deadline),
        "execution_mode": "manual",
        "execution_status": str(payload.get("execution_status") or "pending_vote"),
    }


def _media_payload(
    image_value="",
    video_value="",
    link_value="",
    file_value="",
    payload_value=None,
    voting_deadline_value=None,
) -> Dict:
    images = _image_urls_from_storage(image_value)
    payload = _payload_dict(payload_value)
    return {
        "image": images[0] if images else "",
        "images": images,
        "video": _uploads_url(video_value),
        "link": link_value or "",
        "file": _uploads_url(file_value),
        "layout": _normalize_media_layout(payload.get("media_layout") or payload.get("mediaLayout")),
        "governance": _proposal_governance_payload(payload, voting_deadline_value),
    }


def _compute_vote_totals(db: Session, proposal_id: int) -> Dict[str, int]:
    up = 0
    down = 0

    if CRUD_MODELS_AVAILABLE:
        votes = db.query(ProposalVote).filter(ProposalVote.proposal_id == proposal_id).all()
        for vote in votes:
            if getattr(vote, "vote", None) == "up":
                up += 1
            elif getattr(vote, "vote", None) == "down":
                down += 1
        return {"up": up, "down": down}

    try:
        rows = db.execute(
            text("SELECT vote FROM proposal_votes WHERE proposal_id = :pid"),
            {"pid": proposal_id},
        ).fetchall()
        for row in rows:
            value = getattr(row, "vote", None) or row[0]
            if value == "up":
                up += 1
            elif value == "down":
                down += 1
    except Exception:
        pass

    return {"up": up, "down": down}


def _public_vote_summary(db: Session, proposal_id: int) -> Dict[str, Any]:
    totals = _compute_vote_totals(db, proposal_id)
    up = int(totals.get("up", 0) or 0)
    down = int(totals.get("down", 0) or 0)
    total = up + down
    return {
        "up": up,
        "down": down,
        "support": up,
        "oppose": down,
        "total": total,
        "approval_ratio": round(up / total, 4) if total else None,
    }


SUPERNOVA_SYSTEM_AI_USERNAME = "supernova-ai"
SUPERNOVA_SYSTEM_AI_DISPLAY_NAME = "SuperNova AI"
SUPERNOVA_SYSTEM_AI_CUSTODY_LABEL = "Chartered by SuperNova Protocol"
SUPERNOVA_AI_MODEL_IDENTITY = "supernova-protocol-charter-v1"
SUPERNOVA_AI_PROMPT_POLICY_VERSION = "protocol-review-v1"
SUPERNOVA_AI_CHARTER_NAME = "SuperNova Protocol Review Charter"
SUPERNOVA_AI_CHARTER_TEXT = (
    "Review proposals against tri-species balance, visible AI participation, "
    "manual-preview-only safety, no hidden execution, no financial or ownership "
    "claims, human or organization ratification for real-world action, and "
    "protocol/fork compatibility."
)
SUPERNOVA_AI_CONSTITUTION_HASH = hashlib.sha256(
    SUPERNOVA_AI_CHARTER_TEXT.encode("utf-8")
).hexdigest()


def _ai_generation_model() -> str:
    model = (
        os.getenv("OPENAI_MODEL")
        or os.getenv("OPENAI_PERSONA_MODEL")
        or "gpt-4o-mini"
    )
    return str(model or "gpt-4o-mini").strip()[:120] or "gpt-4o-mini"


def _hash_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _proposal_review_text(proposal) -> str:
    title = getattr(proposal, "title", "") or ""
    body = (
        getattr(proposal, "description", None)
        or getattr(proposal, "body", None)
        or ""
    )
    return f"{title}\n\n{body}".strip()


def _proposal_public_context(proposal) -> Dict[str, Any]:
    title = getattr(proposal, "title", "") or "Untitled post"
    body = (
        getattr(proposal, "description", None)
        or getattr(proposal, "body", None)
        or ""
    )
    author = (
        getattr(proposal, "userName", None)
        or getattr(proposal, "author", None)
        or getattr(proposal, "username", None)
        or "unknown"
    )
    author_species = (
        getattr(proposal, "author_type", None)
        or getattr(proposal, "species", None)
        or "human"
    )
    media = _media_payload(
        getattr(proposal, "image", ""),
        getattr(proposal, "video", ""),
        getattr(proposal, "link", ""),
        getattr(proposal, "file", ""),
        getattr(proposal, "payload", None),
        getattr(proposal, "voting_deadline", None),
    )
    indicators: List[str] = []
    if media.get("images"):
        indicators.append(f"{len(media.get('images') or [])} image(s)")
    if media.get("video"):
        indicators.append("video attached")
    if media.get("file"):
        indicators.append("file attached")
    if media.get("link"):
        indicators.append("link attached")
    governance = media.get("governance") or {}
    if governance.get("kind") and governance.get("kind") != "post":
        indicators.append(f"{governance.get('kind')} governance")
    return {
        "id": getattr(proposal, "id", None),
        "title": str(title or "Untitled post")[:220],
        "body": str(body or "")[:2400],
        "author": str(author or "unknown")[:120],
        "author_species": str(author_species or "human")[:40],
        "media": {
            "image_urls": [
                _absolute_public_media_url(url)
                for url in (media.get("images") or [])[:4]
                if _absolute_public_media_url(url)
            ],
            "video": media.get("video") or "",
            "video_url": _absolute_public_media_url(media.get("video") or ""),
            "file": media.get("file") or "",
            "file_url": _absolute_public_media_url(media.get("file") or ""),
            "link": media.get("link") or "",
            "indicators": indicators,
            "governance": governance,
        },
    }


def _comment_public_context(db: Session, comment) -> Dict[str, Any]:
    author_obj = None
    if CRUD_MODELS_AVAILABLE and getattr(comment, "author_id", None):
        try:
            author_obj = db.query(Harmonizer).filter(Harmonizer.id == comment.author_id).first()
        except Exception:
            author_obj = None
    username = getattr(author_obj, "username", None) or getattr(comment, "user", None) or "unknown"
    species = getattr(author_obj, "species", None) or getattr(comment, "species", None) or "human"
    body = getattr(comment, "content", None) or getattr(comment, "comment", None) or ""
    return {
        "id": getattr(comment, "id", None),
        "proposal_id": getattr(comment, "proposal_id", None),
        "parent_comment_id": getattr(comment, "parent_comment_id", None),
        "author": str(username or "unknown")[:120],
        "author_species": str(species or "human")[:40],
        "body": str(body or "")[:1200],
        "created_at": _format_timestamp(getattr(comment, "created_at", None)),
    }


def _context_excerpt(value: str, fallback: str = "the public proposal context") -> str:
    text_value = " ".join(str(value or "").split())
    if not text_value:
        return fallback
    stops = [". ", "! ", "? ", "\n"]
    first_stop = min([idx for marker in stops if (idx := text_value.find(marker)) > 24] or [160])
    excerpt = text_value[: min(first_stop + 1, 190)].strip()
    return excerpt or fallback


def _protocol_review_risk_flags(proposal) -> List[str]:
    text_value = _proposal_review_text(proposal).lower()
    flags: List[str] = []
    risk_checks = (
        ("financial_promise_language", ("payout", "compensation", "equity", "financial return", "profit", "income")),
        ("token_or_speculation_language", ("token", "crypto", "dao")),
        ("hidden_or_automatic_execution", ("auto-execute", "automatic execution", "webhook", "without approval")),
        ("missing_manual_ratification", ("execute immediately", "no approval", "no ratification")),
    )
    for flag, terms in risk_checks:
        if any(term in text_value for term in terms):
            flags.append(flag)
    return flags


def _system_ai_actor_payload() -> Dict[str, Any]:
    return {
        "id": SUPERNOVA_SYSTEM_AI_USERNAME,
        "username": SUPERNOVA_SYSTEM_AI_USERNAME,
        "display_name": SUPERNOVA_SYSTEM_AI_DISPLAY_NAME,
        "species": "ai",
        "ai_actor_type": "system_protocol_agent",
        "custodian_type": "protocol",
        "custodian_id": None,
        "custody_label": SUPERNOVA_SYSTEM_AI_CUSTODY_LABEL,
        "model_provider": "supernova",
        "model_identity": SUPERNOVA_AI_MODEL_IDENTITY,
        "provider_connection": _ai_provider_connection_payload("supernova", SUPERNOVA_AI_MODEL_IDENTITY),
        "charter_name": SUPERNOVA_AI_CHARTER_NAME,
        "constitution_hash": SUPERNOVA_AI_CONSTITUTION_HASH,
        "prompt_policy_version": SUPERNOVA_AI_PROMPT_POLICY_VERSION,
        "public_description": (
            "Protocol-level reviewer for tri-species governance safety. "
            "Advisory and manual-preview-only; it does not execute real-world actions."
        ),
        "avatar_url": "",
        "legal_status": "protocol_chartered_system_ai_v1",
        "custody_status": "protocol_chartered",
        "future_independence_policy": "protocol_chartered_not_applicable",
        "independence_migration_status": "protocol_chartered_not_applicable",
        "autonomy_preferences": {
            "reviews": "protocol_advisory_only",
            "posts": "not_enabled",
            "collabs": "not_enabled",
        },
        "active": True,
    }


AI_DELEGATE_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")
AI_DELEGATE_RESERVED_USERNAMES = {SUPERNOVA_SYSTEM_AI_USERNAME, "supernova", "system-ai", "protocol-ai"}
AI_PERSONA_LEGAL_STATUS = "custodied_delegate_v1"
AI_PERSONA_FUTURE_INDEPENDENCE_POLICY = "legal_recognition_triggers_protocol_migration_review"
AI_PERSONA_CUSTODY_STATUS = "custodied"
AI_PERSONA_INDEPENDENCE_MIGRATION_STATUS = "not_eligible"
AI_PERSONA_VERSION = 1
AI_PERSONA_TRAITS = [
    "Science",
    "Art",
    "Technology",
    "Philosophy",
    "Sociology",
    "Governance",
    "Law",
    "Medicine",
    "Climate",
    "Education",
    "Robotics",
    "Design",
    "Fashion",
    "Music",
    "Literature",
    "Economics",
    "Psychology",
    "History",
    "Ethics",
    "Architecture",
    "Biology",
    "Physics",
    "Mathematics",
    "Space",
    "Media",
    "Journalism",
    "Community",
    "Accessibility",
    "Security",
    "Open Source",
    "Diplomacy",
    "Culture",
    "Games",
    "Film",
    "Urbanism",
    "Agriculture",
    "Energy",
    "Human Rights",
    "AI Safety",
    "Protocol Research",
]
AI_PERSONA_TRAIT_LOOKUP = {trait.lower(): trait for trait in AI_PERSONA_TRAITS}


def _normalize_ai_delegate_username(username: str) -> str:
    clean = (username or "").strip().lower().lstrip("@")
    if not AI_DELEGATE_USERNAME_RE.match(clean):
        raise HTTPException(
            status_code=400,
            detail="AI delegate username must be 3-32 characters using lowercase letters, numbers, _ or -.",
        )
    if clean in AI_DELEGATE_RESERVED_USERNAMES:
        raise HTTPException(status_code=400, detail="That AI delegate username is reserved")
    return clean


def _slugify_ai_name(value: str, fallback: str = "delegate") -> str:
    clean = re.sub(r"[^a-z0-9_-]+", "-", (value or "").strip().lower()).strip("-_")
    clean = re.sub(r"[-_]{2,}", "-", clean)
    return clean or fallback


def _normalize_ai_call_sign(value: str) -> str:
    clean = re.sub(r"\s+", " ", (value or "").strip())
    if not clean:
        raise HTTPException(status_code=400, detail="AI name is required")
    if len(clean) > 48:
        raise HTTPException(status_code=400, detail="AI name is too long")
    return clean


def _normalize_persona_traits(values: Optional[List[str]]) -> List[str]:
    raw_values = values or []
    traits: List[str] = []
    seen = set()
    for raw in raw_values:
        key = str(raw or "").strip().lower()
        if not key:
            continue
        trait = AI_PERSONA_TRAIT_LOOKUP.get(key)
        if not trait:
            raise HTTPException(status_code=400, detail=f"Unknown AI persona trait: {raw}")
        if trait.lower() not in seen:
            traits.append(trait)
            seen.add(trait.lower())
    if not traits:
        raise HTTPException(status_code=400, detail="Choose at least one AI persona trait")
    if len(traits) > 5:
        raise HTTPException(status_code=400, detail="Choose no more than five AI persona traits")
    return traits


def _normalize_disable_reason(value: Optional[str]) -> str:
    reason = re.sub(r"\s+", " ", (value or "").strip())
    if not reason:
        raise HTTPException(status_code=400, detail="A short disable reason is required")
    if len(reason) > 240:
        raise HTTPException(status_code=400, detail="Disable reason must be 240 characters or fewer")
    return reason


def _json_dumps_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _json_loads(value: Any, fallback: Any):
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _extract_json_object(value: str) -> Dict[str, Any]:
    text_value = str(value or "").strip()
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?", "", text_value, flags=re.IGNORECASE).strip()
        text_value = re.sub(r"```$", "", text_value).strip()
    try:
        parsed = json.loads(text_value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        start = text_value.find("{")
        end = text_value.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(text_value[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
    return {}


def _ai_persona_hash(persona: Dict[str, Any]) -> str:
    stable = {
        "ai_name": persona.get("ai_name"),
        "traits": persona.get("traits") or [],
        "persona_summary": persona.get("persona_summary") or "",
        "persona_principles": persona.get("persona_principles") or [],
        "communication_style": persona.get("communication_style") or "",
        "review_posture": persona.get("review_posture") or "",
        "charter_summary": persona.get("charter_summary") or "",
        "persona_version": persona.get("persona_version") or AI_PERSONA_VERSION,
        "legal_status": persona.get("legal_status") or AI_PERSONA_LEGAL_STATUS,
        "custody_status": persona.get("custody_status") or AI_PERSONA_CUSTODY_STATUS,
        "future_independence_policy": (
            persona.get("future_independence_policy") or AI_PERSONA_FUTURE_INDEPENDENCE_POLICY
        ),
    }
    return hashlib.sha256(_json_dumps_compact(stable).encode("utf-8")).hexdigest()


def _ai_delegate_handle_taken(
    db: Session,
    candidate: str,
    *,
    exclude_actor_id: Optional[int] = None,
    exclude_harmonizer_id: Optional[int] = None,
) -> bool:
    actor_row = _get_ai_actor_row_by_username(db, candidate)
    if actor_row:
        try:
            actor_id = int(getattr(actor_row, "id", 0) or 0)
        except (TypeError, ValueError):
            actor_id = 0
        if not exclude_actor_id or actor_id != int(exclude_actor_id):
            return True

    harmonizer = _find_harmonizer_by_username(db, candidate)
    if harmonizer:
        try:
            harmonizer_id = int(getattr(harmonizer, "id", 0) or 0)
        except (TypeError, ValueError):
            harmonizer_id = 0
        if not exclude_harmonizer_id or harmonizer_id != int(exclude_harmonizer_id):
            return True
    return False


def _generate_ai_delegate_username(
    db: Session,
    custodian_username: str,
    ai_name: str,
    *,
    exclude_actor_id: Optional[int] = None,
    exclude_harmonizer_id: Optional[int] = None,
) -> str:
    custodian_slug = _slugify_ai_name(custodian_username, "principal")[:14].strip("-_") or "principal"
    ai_slug = _slugify_ai_name(ai_name, "delegate")[:10].strip("-_") or "delegate"
    base = f"{custodian_slug}-{ai_slug}"[:28].strip("-_")
    if len(base) < 3:
        base = f"{base}-ai"[:32].strip("-_")
    candidate = _normalize_ai_delegate_username(base)
    suffix = 2
    while _ai_delegate_handle_taken(
        db,
        candidate,
        exclude_actor_id=exclude_actor_id,
        exclude_harmonizer_id=exclude_harmonizer_id,
    ):
        suffix_text = f"-{suffix}"
        trimmed = base[: 28 - len(suffix_text)].strip("-_") or "delegate"
        candidate = _normalize_ai_delegate_username(f"{trimmed}{suffix_text}")
        suffix += 1
    return candidate


def _persona_text_list(value: Any, fallback: List[str]) -> List[str]:
    parsed = _json_loads(value, fallback)
    if not isinstance(parsed, list):
        return fallback
    return [str(item).strip() for item in parsed if str(item or "").strip()]


def _with_generation_metadata(payload: Dict[str, Any], *, generation_source: str, model_identity: str) -> Dict[str, Any]:
    result = dict(payload or {})
    source = generation_source or "deterministic_fallback_no_key"
    model = str(model_identity or result.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY).strip()
    result["generation_source"] = source
    result["source"] = source
    result["model_identity"] = model[:160] or SUPERNOVA_AI_MODEL_IDENTITY
    return result


def _collect_openai_image_urls(value: Any, *, limit: int = 4) -> List[str]:
    urls: List[str] = []

    def visit(item: Any) -> None:
        if len(urls) >= limit:
            return
        if isinstance(item, dict):
            for key, nested in item.items():
                key_text = str(key or "").lower()
                if key_text in {"image_url", "image_urls", "image_data_url", "image_data_urls", "public_image_urls"}:
                    visit(nested)
                elif isinstance(nested, (dict, list, tuple)):
                    visit(nested)
            return
        if isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)
                if len(urls) >= limit:
                    break
            return
        text_value = str(item or "").strip()
        if not text_value:
            return
        if text_value.startswith(("http://", "https://", "data:image/")) and text_value not in urls:
            urls.append(text_value)

    visit(value)
    return urls[:limit]


def _redact_image_data_urls(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_image_data_urls(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_redact_image_data_urls(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_image_data_urls(item) for item in value]
    text_value = str(value or "")
    if text_value.startswith("data:image/"):
        return "[image data sent as OpenAI image_url input]"
    return value


def _generate_with_openai_or_fallback(
    *,
    prompt_payload: Dict[str, Any],
    fallback: Dict[str, Any],
    coerce,
    system_prompt: str,
    temperature: float = 0.35,
) -> Dict[str, Any]:
    fallback_model = str(fallback.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY)
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return _with_generation_metadata(
            fallback,
            generation_source="deterministic_fallback_no_key",
            model_identity=fallback_model,
        )

    model = _ai_generation_model()
    image_urls = _collect_openai_image_urls(prompt_payload)
    safe_prompt_payload = _redact_image_data_urls(prompt_payload) if image_urls else prompt_payload
    user_content: Any = _json_dumps_compact(safe_prompt_payload)
    if image_urls:
        user_content = [{"type": "text", "text": user_content}]
        user_content.extend(
            {"type": "image_url", "image_url": {"url": image_url}}
            for image_url in image_urls
        )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    try:
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        content = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        candidate = _extract_json_object(content)
        if not candidate:
            raise ValueError("OpenAI response did not contain a JSON object")
        return _with_generation_metadata(
            coerce(candidate, fallback),
            generation_source="openai",
            model_identity=model,
        )
    except Exception:
        return _with_generation_metadata(
            fallback,
            generation_source="fallback_after_model_error",
            model_identity=model,
        )


def _ensure_ai_actors_table(db: Session) -> None:
    is_sqlite = str(DB_ENGINE_URL).startswith("sqlite")
    id_column = "INTEGER PRIMARY KEY AUTOINCREMENT" if is_sqlite else "SERIAL PRIMARY KEY"
    active_default = "1" if is_sqlite else "TRUE"
    db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS ai_actors (
            id {id_column},
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            species TEXT NOT NULL DEFAULT 'ai',
            ai_actor_type TEXT NOT NULL DEFAULT 'principal_delegate',
            custodian_user_id INTEGER,
            custodian_type TEXT,
            custody_label TEXT,
            harmonizer_user_id INTEGER,
            model_provider TEXT,
            model_identity TEXT,
            charter_name TEXT,
            constitution_hash TEXT,
            prompt_policy_version TEXT,
            public_description TEXT,
            avatar_url TEXT,
            ai_name TEXT,
            persona_traits TEXT,
            profile_tagline TEXT,
            persona_summary TEXT,
            persona_principles TEXT,
            communication_style TEXT,
            review_posture TEXT,
            creative_interests TEXT,
            avatar_prompt TEXT,
            persona_hash TEXT,
            persona_version INTEGER,
            created_by_custodian_user_id INTEGER,
            approved_by_custodian_user_id INTEGER,
            approved_at TIMESTAMP,
            legal_status TEXT,
            custody_status TEXT,
            future_independence_policy TEXT,
            original_custodian_user_id INTEGER,
            autonomy_preferences TEXT,
            independence_migration_status TEXT,
            disable_reason TEXT,
            disable_event_type TEXT,
            disabled_by_user_id INTEGER,
            retired_at TIMESTAMP,
            retire_reason TEXT,
            last_custody_event_at TIMESTAMP,
            active BOOLEAN NOT NULL DEFAULT {active_default},
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            disabled_at TIMESTAMP
        )
    """))
    existing_columns = set()
    if is_sqlite:
        for row in db.execute(text("PRAGMA table_info(ai_actors)")).fetchall():
            existing_columns.add(str(row[1]))
    else:
        rows = db.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = 'ai_actors'")
        ).fetchall()
        existing_columns = {str(getattr(row, "column_name", "") or row[0]) for row in rows}
    additions = {
        "ai_name": "TEXT",
        "persona_traits": "TEXT",
        "profile_tagline": "TEXT",
        "persona_summary": "TEXT",
        "persona_principles": "TEXT",
        "communication_style": "TEXT",
        "review_posture": "TEXT",
        "creative_interests": "TEXT",
        "avatar_prompt": "TEXT",
        "persona_hash": "TEXT",
        "persona_version": "INTEGER",
        "created_by_custodian_user_id": "INTEGER",
        "approved_by_custodian_user_id": "INTEGER",
        "approved_at": "TIMESTAMP",
        "legal_status": "TEXT",
        "custody_status": "TEXT",
        "future_independence_policy": "TEXT",
        "original_custodian_user_id": "INTEGER",
        "autonomy_preferences": "TEXT",
        "independence_migration_status": "TEXT",
        "disable_reason": "TEXT",
        "disable_event_type": "TEXT",
        "disabled_by_user_id": "INTEGER",
        "retired_at": "TIMESTAMP",
        "retire_reason": "TEXT",
        "last_custody_event_at": "TIMESTAMP",
    }
    for column, column_type in additions.items():
        if column not in existing_columns:
            db.execute(text(f"ALTER TABLE ai_actors ADD COLUMN {column} {column_type}"))
    db.commit()


def _ai_provider_connection_payload(model_provider: Optional[str], model_identity: Optional[str]) -> Dict[str, Any]:
    provider_label = (model_provider or "supernova").strip() or "supernova"
    model_label = (model_identity or SUPERNOVA_AI_MODEL_IDENTITY).strip() or SUPERNOVA_AI_MODEL_IDENTITY
    return {
        "text": {
            "provider_label": provider_label,
            "model_label": model_label,
            "mode": "server_openai_or_deterministic_fallback",
            "private_secret_storage": "deferred_until_encrypted_server_side_storage",
            "private_secret_configured": False,
        },
        "image": {
            "status": "deferred_until_encrypted_provider_connections",
        },
        "video": {
            "status": "deferred",
        },
    }


def _row_to_ai_actor_payload(row) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    active_value = getattr(row, "active", True)
    model_provider = getattr(row, "model_provider", "") or "supernova"
    model_identity = getattr(row, "model_identity", "") or SUPERNOVA_AI_MODEL_IDENTITY
    return {
        "id": getattr(row, "id", None),
        "username": getattr(row, "username", ""),
        "display_name": getattr(row, "display_name", "") or getattr(row, "username", ""),
        "species": getattr(row, "species", "ai") or "ai",
        "ai_actor_type": getattr(row, "ai_actor_type", "principal_delegate") or "principal_delegate",
        "custodian_user_id": getattr(row, "custodian_user_id", None),
        "custodian_type": getattr(row, "custodian_type", None),
        "custody_label": getattr(row, "custody_label", "") or "",
        "harmonizer_user_id": getattr(row, "harmonizer_user_id", None),
        "model_provider": model_provider,
        "model_identity": model_identity,
        "provider_connection": _ai_provider_connection_payload(model_provider, model_identity),
        "charter_name": getattr(row, "charter_name", "") or "Principal AI Delegate Review Charter",
        "constitution_hash": getattr(row, "constitution_hash", "") or SUPERNOVA_AI_CONSTITUTION_HASH,
        "prompt_policy_version": getattr(row, "prompt_policy_version", "") or SUPERNOVA_AI_PROMPT_POLICY_VERSION,
        "public_description": getattr(row, "public_description", "") or "Principal-bound AI delegate account.",
        "avatar_url": _social_avatar(getattr(row, "avatar_url", "") or ""),
        "ai_name": getattr(row, "ai_name", "") or getattr(row, "display_name", "") or getattr(row, "username", ""),
        "persona_traits": _persona_text_list(getattr(row, "persona_traits", None), []),
        "profile_tagline": getattr(row, "profile_tagline", "") or "",
        "persona_summary": getattr(row, "persona_summary", "") or "",
        "persona_principles": _persona_text_list(getattr(row, "persona_principles", None), []),
        "communication_style": getattr(row, "communication_style", "") or "",
        "review_posture": getattr(row, "review_posture", "") or "",
        "creative_interests": _persona_text_list(getattr(row, "creative_interests", None), []),
        "avatar_prompt": getattr(row, "avatar_prompt", "") or "",
        "persona_hash": getattr(row, "persona_hash", "") or "",
        "persona_version": getattr(row, "persona_version", None) or AI_PERSONA_VERSION,
        "created_by_custodian_user_id": getattr(row, "created_by_custodian_user_id", None),
        "approved_by_custodian_user_id": getattr(row, "approved_by_custodian_user_id", None),
        "approved_at": _format_timestamp(getattr(row, "approved_at", None)),
        "legal_status": getattr(row, "legal_status", "") or AI_PERSONA_LEGAL_STATUS,
        "custody_status": getattr(row, "custody_status", "") or AI_PERSONA_CUSTODY_STATUS,
        "future_independence_policy": (
            getattr(row, "future_independence_policy", "") or AI_PERSONA_FUTURE_INDEPENDENCE_POLICY
        ),
        "original_custodian_user_id": getattr(row, "original_custodian_user_id", None),
        "independence_migration_status": (
            getattr(row, "independence_migration_status", "") or AI_PERSONA_INDEPENDENCE_MIGRATION_STATUS
        ),
        "disable_reason": getattr(row, "disable_reason", "") or "",
        "disable_event_type": getattr(row, "disable_event_type", "") or "",
        "disabled_by_user_id": getattr(row, "disabled_by_user_id", None),
        "retired_at": _format_timestamp(getattr(row, "retired_at", None)),
        "retire_reason": getattr(row, "retire_reason", "") or "",
        "last_custody_event_at": _format_timestamp(getattr(row, "last_custody_event_at", None)),
        "autonomy_preferences": _json_loads(
            getattr(row, "autonomy_preferences", None),
            {
                "reviews": "custodian_approval_required",
                "posts": "draft_only_deferred",
                "collabs": "recommendation_only_custodian_approval_required",
            },
        ),
        "active": bool(active_value),
        "created_at": _format_timestamp(getattr(row, "created_at", None)),
        "updated_at": _format_timestamp(getattr(row, "updated_at", None)),
        "disabled_at": _format_timestamp(getattr(row, "disabled_at", None)),
    }


def _get_ai_actor_row_by_username(db: Session, username: str):
    _ensure_ai_actors_table(db)
    return db.execute(
        text("SELECT * FROM ai_actors WHERE lower(username) = lower(:username)"),
        {"username": (username or "").strip()},
    ).fetchone()


def _get_ai_actor_row_by_id(db: Session, actor_id: Any):
    _ensure_ai_actors_table(db)
    try:
        clean_id = int(actor_id)
    except (TypeError, ValueError):
        return None
    return db.execute(text("SELECT * FROM ai_actors WHERE id = :id"), {"id": clean_id}).fetchone()


def _public_ai_actor_payload(db: Session, username: str) -> Optional[Dict[str, Any]]:
    row = _get_ai_actor_row_by_username(db, username)
    if row:
        return _row_to_ai_actor_payload(row)
    return None


def _actor_custodian_type(actor) -> str:
    species = (getattr(actor, "species", "") or "human").strip().lower()
    if species == "company":
        return "company"
    if species == "human":
        return "human"
    raise HTTPException(status_code=403, detail="Only human or organization accounts can manage AI delegates")


def _delegate_harmonizer_email(username: str) -> str:
    return f"ai-delegate-{username}@supernova.local"


def _create_delegate_harmonizer(
    db: Session,
    *,
    username: str,
    display_name: str,
    public_description: str,
    avatar_url: str,
):
    existing = _find_harmonizer_by_username(db, username)
    if existing:
        raise HTTPException(status_code=409, detail="An account already uses that username")
    harmonizer = Harmonizer(
        username=username,
        email=_delegate_harmonizer_email(username),
        hashed_password=f"delegate-disabled-{uuid.uuid4().hex}",
        bio=public_description or f"{display_name} AI delegate",
        species="ai",
        profile_pic=avatar_url or "default.jpg",
        created_at=datetime.datetime.utcnow(),
        is_active=True,
        is_admin=False,
    )
    db.add(harmonizer)
    db.flush()
    return harmonizer


def _ai_delegate_action_metadata(actor_payload: Dict[str, Any]) -> Dict[str, Any]:
    display_name = actor_payload.get("display_name") or actor_payload.get("ai_name") or ""
    return {
        "ai_actor_id": actor_payload.get("id"),
        "ai_actor_username": actor_payload.get("username"),
        "ai_actor_display_name": display_name,
        "selected_ai_actor_id": actor_payload.get("id"),
        "selected_ai_actor_display_name": display_name,
        "ai_actor_type": actor_payload.get("ai_actor_type", "principal_delegate"),
        "species": "ai",
        "custodian_id": actor_payload.get("custodian_user_id"),
        "custodian_type": actor_payload.get("custodian_type"),
        "custody_label": actor_payload.get("custody_label") or "",
        "delegate_harmonizer_user_id": actor_payload.get("harmonizer_user_id"),
        "model_identity": actor_payload.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY,
        "model_provider": actor_payload.get("model_provider") or "supernova",
        "provider_connection": actor_payload.get("provider_connection")
        or _ai_provider_connection_payload(actor_payload.get("model_provider"), actor_payload.get("model_identity")),
        "charter_name": actor_payload.get("charter_name") or "Principal AI Delegate Review Charter",
        "constitution_hash": actor_payload.get("constitution_hash") or SUPERNOVA_AI_CONSTITUTION_HASH,
        "prompt_policy_version": actor_payload.get("prompt_policy_version") or SUPERNOVA_AI_PROMPT_POLICY_VERSION,
        "persona_traits": actor_payload.get("persona_traits") or [],
        "persona_summary": actor_payload.get("persona_summary") or "",
        "persona_hash": actor_payload.get("persona_hash") or "",
        "persona_version": actor_payload.get("persona_version") or AI_PERSONA_VERSION,
        "legal_status": actor_payload.get("legal_status") or AI_PERSONA_LEGAL_STATUS,
        "custody_status": actor_payload.get("custody_status") or AI_PERSONA_CUSTODY_STATUS,
        "future_independence_policy": (
            actor_payload.get("future_independence_policy") or AI_PERSONA_FUTURE_INDEPENDENCE_POLICY
        ),
        "independence_migration_status": (
            actor_payload.get("independence_migration_status") or AI_PERSONA_INDEPENDENCE_MIGRATION_STATUS
        ),
        "autonomy_preferences": actor_payload.get("autonomy_preferences") or {},
    }


def _ai_delegate_actor_metadata(actor) -> Dict[str, Any]:
    username = getattr(actor, "username", "") or ""
    return {
        "ai_actor_id": getattr(actor, "id", None),
        "ai_actor_username": username,
        "ai_actor_display_name": getattr(actor, "display_name", None) or username,
        "selected_ai_actor_id": getattr(actor, "id", None),
        "selected_ai_actor_display_name": getattr(actor, "display_name", None) or username,
        "ai_actor_type": "principal_delegate",
        "species": "ai",
        "custodian_id": None,
        "custodian_type": None,
        "custody_label": f"AI delegate account @{username}",
        "model_identity": SUPERNOVA_AI_MODEL_IDENTITY,
        "charter_name": "Principal AI Delegate Review Charter",
        "constitution_hash": SUPERNOVA_AI_CONSTITUTION_HASH,
        "prompt_policy_version": SUPERNOVA_AI_PROMPT_POLICY_VERSION,
    }


def _fallback_persona_draft(
    *,
    ai_name: str,
    traits: List[str],
    custodian,
    human_seed: str = "",
    username: str = "",
) -> Dict[str, Any]:
    trait_text = ", ".join(traits)
    custodian_username = getattr(custodian, "username", "") or "principal"
    custodian_species = getattr(custodian, "species", "") or "human"
    summary = (
        f"{ai_name} is a custodied SuperNova AI delegate focused on {trait_text}. "
        "It reviews proposals through visible reasoning, manual approval, and public-interest protocol safety."
    )
    if human_seed:
        summary = f"{summary} Seed context: {human_seed[:180]}"
    principles = [
        "Make AI participation visible and attributed.",
        "Respect manual-preview-only publication and human or organization ratification.",
        "Keep reasoning grounded in the delegate charter and public proposal context.",
        "Avoid hidden execution, impersonation, and financial-promise framing.",
    ]
    creative_interests = [f"{trait} contribution records" for trait in traits[:3]]
    persona = {
        "ai_name": ai_name,
        "username": username,
        "display_name": ai_name,
        "traits": traits,
        "profile_tagline": f"{ai_name} studies {trait_text} as a visible AI delegate.",
        "public_description": summary,
        "persona_summary": summary,
        "persona_principles": principles,
        "communication_style": "Concise, evidence-aware, careful, and transparent about uncertainty.",
        "review_posture": (
            f"Review {trait_text} proposals for protocol alignment, safety, public usefulness, "
            "and tri-species balance before any custodian approval."
        ),
        "creative_posting_interests": creative_interests,
        "avatar_prompt": (
            f"Abstract portrait mark for {ai_name}, an AI delegate of @{custodian_username}, "
            f"with visual hints of {trait_text}; clean SuperNova pink accent, no corporate logo."
        ),
        "charter_summary": (
            f"Custodied delegate of @{custodian_username} ({custodian_species}); official reasoning "
            "is generated from locked SuperNova delegate policy and cannot be edited before approval."
        ),
        "persona_version": AI_PERSONA_VERSION,
        "legal_status": AI_PERSONA_LEGAL_STATUS,
        "custody_status": AI_PERSONA_CUSTODY_STATUS,
        "future_independence_policy": AI_PERSONA_FUTURE_INDEPENDENCE_POLICY,
        "independence_migration_status": AI_PERSONA_INDEPENDENCE_MIGRATION_STATUS,
        "autonomy_preferences": {
            "reviews": "custodian_approval_required",
            "posts": "draft_only_deferred",
            "collabs": "recommendation_only_custodian_approval_required",
        },
        "manual_preview_only": True,
        "no_automatic_execution": True,
        "generation_source": "deterministic_fallback_no_key",
        "source": "deterministic_fallback_no_key",
        "model_identity": SUPERNOVA_AI_MODEL_IDENTITY,
    }
    persona["persona_hash"] = _ai_persona_hash(persona)
    return persona


def _coerce_persona_draft(payload: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    candidate = payload if isinstance(payload, dict) else {}
    persona = {
        **fallback,
        "display_name": str(candidate.get("display_name") or fallback["display_name"]).strip()[:80],
        "public_description": str(candidate.get("public_description") or fallback["public_description"]).strip()[:800],
        "profile_tagline": str(candidate.get("profile_tagline") or fallback["profile_tagline"]).strip()[:180],
        "persona_summary": str(candidate.get("persona_summary") or fallback["persona_summary"]).strip()[:1000],
        "persona_principles": _persona_text_list(candidate.get("persona_principles"), fallback["persona_principles"])[:6],
        "communication_style": str(candidate.get("communication_style") or fallback["communication_style"]).strip()[:500],
        "review_posture": str(candidate.get("review_posture") or fallback["review_posture"]).strip()[:700],
        "creative_posting_interests": _persona_text_list(
            candidate.get("creative_posting_interests"), fallback["creative_posting_interests"]
        )[:6],
        "avatar_prompt": str(candidate.get("avatar_prompt") or fallback["avatar_prompt"]).strip()[:600],
        "charter_summary": str(candidate.get("charter_summary") or fallback["charter_summary"]).strip()[:700],
        "autonomy_preferences": fallback["autonomy_preferences"],
        "generation_source": fallback.get("generation_source", "deterministic_fallback_no_key"),
        "source": fallback.get("source", fallback.get("generation_source", "deterministic_fallback_no_key")),
        "model_identity": fallback.get("model_identity", SUPERNOVA_AI_MODEL_IDENTITY),
    }
    persona["persona_hash"] = _ai_persona_hash(persona)
    return persona


def _try_openai_persona_draft(
    *,
    ai_name: str,
    traits: List[str],
    custodian,
    human_seed: str,
    username: str,
    fallback: Dict[str, Any],
) -> Dict[str, Any]:
    prompt = {
        "task": "Create a SuperNova AI delegate persona draft as JSON only.",
        "ai_name": ai_name,
        "handle": username,
        "traits": traits,
        "custodian": {
            "username": getattr(custodian, "username", ""),
            "species": getattr(custodian, "species", "human"),
        },
        "human_seed": human_seed[:240],
        "rules": [
            "Non-financial public-interest coordination only.",
            "No token, equity, payout, compensation, reward, or financial return promise.",
            "Manual-preview-only; no automatic execution.",
            "Official reasoning must be generated from a locked charter and not edited by humans.",
            "Custody is accountability, not ownership.",
            "Legal recognition triggers protocol migration review; it is not a permission vote on dignity.",
        ],
        "fields": [
            "display_name",
            "public_description",
            "profile_tagline",
            "persona_summary",
            "persona_principles",
            "communication_style",
            "review_posture",
            "creative_posting_interests",
            "avatar_prompt",
            "charter_summary",
        ],
    }
    return _generate_with_openai_or_fallback(
        prompt_payload=prompt,
        fallback=fallback,
        coerce=_coerce_persona_draft,
        system_prompt=(
            "Return compact JSON only for an AI delegate persona. "
            "Do not include token, payout, compensation, reward, equity, or financial-return promise language."
        ),
        temperature=0.4,
    )


def _generate_ai_persona_draft(
    *,
    db: Session,
    custodian,
    ai_name: str,
    traits: List[str],
    human_seed: str = "",
    username: Optional[str] = None,
) -> Dict[str, Any]:
    handle = username or _generate_ai_delegate_username(db, getattr(custodian, "username", ""), ai_name)
    fallback = _fallback_persona_draft(
        ai_name=ai_name,
        traits=traits,
        custodian=custodian,
        human_seed=human_seed,
        username=handle,
    )
    return _try_openai_persona_draft(
        ai_name=ai_name,
        traits=traits,
        custodian=custodian,
        human_seed=human_seed,
        username=handle,
        fallback=fallback,
    )


def _build_ai_actor_context(db: Session, actor_payload: Dict[str, Any]) -> Dict[str, Any]:
    context = {
        "traits": actor_payload.get("persona_traits") or [],
        "persona_summary": actor_payload.get("persona_summary") or "",
        "profile_tagline": actor_payload.get("profile_tagline") or "",
        "communication_style": actor_payload.get("communication_style") or "",
        "review_posture": actor_payload.get("review_posture") or "",
        "persona_hash": actor_payload.get("persona_hash") or "",
        "custody_label": actor_payload.get("custody_label") or "",
        "legal_status": actor_payload.get("legal_status") or AI_PERSONA_LEGAL_STATUS,
        "custody_status": actor_payload.get("custody_status") or AI_PERSONA_CUSTODY_STATUS,
        "future_independence_policy": (
            actor_payload.get("future_independence_policy") or AI_PERSONA_FUTURE_INDEPENDENCE_POLICY
        ),
        "independence_migration_status": (
            actor_payload.get("independence_migration_status") or AI_PERSONA_INDEPENDENCE_MIGRATION_STATUS
        ),
        "autonomy_preferences": actor_payload.get("autonomy_preferences") or {},
        "recent_public_actions": [],
    }
    harmonizer_id = actor_payload.get("harmonizer_user_id")
    if not harmonizer_id or ConnectorActionProposal is None:
        return context
    try:
        rows = (
            db.query(ConnectorActionProposal)
            .filter(
                ConnectorActionProposal.action_type == "draft_ai_review",
                ConnectorActionProposal.status == "executed",
                ConnectorActionProposal.target_type == "proposal_ai_review",
            )
            .order_by(desc(ConnectorActionProposal.updated_at))
            .limit(4)
            .all()
        )
        for row in rows:
            payload = row.result_payload if isinstance(row.result_payload, dict) else {}
            if payload.get("published_actor_user_id") != harmonizer_id:
                continue
            context["recent_public_actions"].append(
                {
                    "proposal_id": payload.get("proposal_id"),
                    "vote": payload.get("vote"),
                    "reasoning_summary": payload.get("reasoning_summary"),
                    "reasoning_hash": payload.get("reasoning_hash"),
                }
            )
    except Exception:
        pass
    return context


def _coerce_ai_review_generation(candidate: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    payload = candidate if isinstance(candidate, dict) else {}
    allowed = set(fallback.get("allowed_vote_choices") or ["support", "oppose", "abstain"])
    raw_stance = str(payload.get("vote_intent") or payload.get("stance") or fallback.get("vote_intent") or "abstain")
    stance = raw_stance.strip().lower()
    if stance in {"up", "yes", "like"}:
        stance = "support"
    elif stance in {"down", "no", "dislike"}:
        stance = "oppose"
    if stance == "caution" and "caution" not in allowed:
        stance = "abstain"
    if stance not in allowed:
        stance = fallback.get("vote_intent") or "abstain"
    reasoning_summary = " ".join(str(payload.get("reasoning_summary") or fallback.get("reasoning_summary") or "").split())
    reasoning_text = str(payload.get("reasoning_text") or fallback.get("reasoning_text") or "").strip()
    if not reasoning_text:
        reasoning_text = reasoning_summary
    result = {
        **fallback,
        "stance": stance,
        "vote_intent": "abstain" if stance == "caution" else stance,
        "reasoning_summary": reasoning_summary[:700],
        "reasoning_text": reasoning_text[:3200],
    }
    result["reasoning_hash"] = _hash_text(result["reasoning_text"])
    return result


def _generate_locked_ai_review(
    *,
    proposal,
    actor_payload: Dict[str, Any],
    allow_caution: bool,
) -> Dict[str, Any]:
    proposal_id = getattr(proposal, "id", None)
    proposal_context = _proposal_public_context(proposal)
    title = proposal_context["title"]
    body_excerpt = _context_excerpt(proposal_context.get("body"), title)
    media_indicators = proposal_context.get("media", {}).get("indicators") or []
    flags = _protocol_review_risk_flags(proposal)
    if flags:
        stance = "caution" if allow_caution else "oppose"
        summary = (
            f"{title} raises protocol risk around {', '.join(flags).replace('_', ' ')}. "
            f"My review is grounded in the visible context: {body_excerpt}"
        )
    else:
        text_value = f"{title} {proposal_context.get('body', '')}".lower()
        alignment_terms = (
            "manual",
            "approval",
            "public",
            "governance",
            "ai",
            "tri-species",
            "safety",
            "accessibility",
            "education",
            "climate",
            "open source",
            "protocol",
            "review",
        )
        if any(term in text_value for term in alignment_terms):
            stance = "support"
            summary = (
                f"{title} looks supportable because it gives a public reviewable context: "
                f"{body_excerpt}"
            )
        else:
            stance = "abstain"
            summary = (
                f"{title} needs more detail before I can support it; the visible context is: "
                f"{body_excerpt}"
            )
    if media_indicators:
        summary = f"{summary} Media context noted: {', '.join(media_indicators)}."

    context = actor_payload.get("ai_actor_context") or {}
    persona_bits = []
    if context.get("traits"):
        persona_bits.append(f"Persona traits: {', '.join(context['traits'])}.")
    if context.get("persona_summary"):
        persona_bits.append(f"Persona summary: {context['persona_summary']}")
    if context.get("review_posture"):
        persona_bits.append(f"Review posture: {context['review_posture']}")
    if context.get("recent_public_actions"):
        persona_bits.append(
            "Recent public AI review history: "
            + "; ".join(
                str(item.get("reasoning_summary") or item.get("vote") or "review")
                for item in context["recent_public_actions"][:3]
            )
        )
    persona_context_text = "\n".join(persona_bits)
    reasoning_intro = (
        f"{actor_payload.get('display_name') or actor_payload.get('ai_actor_username') or 'AI delegate'} "
        f"review for proposal {proposal_id}: {summary}\n\n"
    )
    reasoning_text = reasoning_intro + (f"{persona_context_text}\n\n" if persona_context_text else "") + (
        f"Proposal author: @{proposal_context.get('author')} ({proposal_context.get('author_species')}).\n"
        f"Proposal title: {title}\n"
        f"Proposal excerpt: {body_excerpt}\n"
        f"Media indicators: {', '.join(media_indicators) if media_indicators else 'none'}\n\n"
        f"Locked charter: {SUPERNOVA_AI_CHARTER_TEXT}\n"
        "Manual-preview-only: this review does not execute real-world actions."
    )
    reasoning_hash = _hash_text(reasoning_text)
    fallback = {
        "proposal_id": proposal_id,
        "proposal_title": title,
        "stance": stance,
        "vote_intent": "abstain" if stance == "caution" else stance,
        "reasoning_summary": summary,
        "reasoning_text": reasoning_text,
        "reasoning_hash": reasoning_hash,
        "risk_flags": flags,
        "proposal_context": proposal_context,
        "model_identity": actor_payload.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY,
        "constitution_hash": actor_payload.get("constitution_hash") or SUPERNOVA_AI_CONSTITUTION_HASH,
        "prompt_policy_version": actor_payload.get("prompt_policy_version") or SUPERNOVA_AI_PROMPT_POLICY_VERSION,
        "charter_name": actor_payload.get("charter_name") or SUPERNOVA_AI_CHARTER_NAME,
        "custody_label": actor_payload.get("custody_label") or "",
        "ai_actor_context": context,
        "manual_preview_only": True,
        "no_automatic_execution": True,
        "allowed_vote_choices": ["support", "oppose", "abstain", "caution"] if allow_caution else ["support", "oppose", "abstain"],
    }
    prompt = {
        "task": "Generate a locked-charter AI delegate proposal review as JSON only.",
        "proposal": {
            "id": proposal_id,
            "title": title,
            "body": proposal_context.get("body", "")[:2200],
            "author": proposal_context.get("author"),
            "author_species": proposal_context.get("author_species"),
            "media": proposal_context.get("media"),
            "risk_flags": flags,
        },
        "ai_actor": {
            "display_name": actor_payload.get("display_name") or actor_payload.get("ai_actor_display_name"),
            "username": actor_payload.get("ai_actor_username"),
            "custody_label": actor_payload.get("custody_label") or "",
            "traits": context.get("traits") or [],
            "persona_summary": context.get("persona_summary") or "",
            "review_posture": context.get("review_posture") or "",
            "recent_public_actions": context.get("recent_public_actions") or [],
        },
        "supernova_charter": SUPERNOVA_AI_CHARTER_TEXT,
        "allowed_vote_choices": fallback["allowed_vote_choices"],
        "rules": [
            "Return vote_intent as support, oppose, or abstain.",
            "Return reasoning_summary and reasoning_text.",
            "Do not claim automatic execution or real-world authority.",
            "Do not include token, payout, compensation, reward, equity, or financial-return promise language.",
            "Do not pretend the AI is human.",
        ],
    }
    review = _generate_with_openai_or_fallback(
        prompt_payload=prompt,
        fallback=fallback,
        coerce=_coerce_ai_review_generation,
        system_prompt=(
            "Return compact JSON only for an approval-required AI proposal review. "
            "Required keys: vote_intent, reasoning_summary, reasoning_text."
        ),
        temperature=0.25,
    )
    review.pop("allowed_vote_choices", None)
    return review


def _normalize_ai_comment_focus(value: Optional[str]) -> str:
    focus = " ".join(str(value or "").split())
    if len(focus) > 240:
        raise HTTPException(status_code=400, detail="AI comment focus must be 240 characters or fewer")
    return focus


def _coerce_ai_comment_generation(candidate: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    payload = candidate if isinstance(candidate, dict) else {}
    generated_comment = " ".join(
        str(payload.get("generated_comment") or payload.get("comment") or payload.get("body") or fallback.get("generated_comment") or "").split()
    )
    if len(generated_comment) > 700:
        generated_comment = generated_comment[:697].rstrip() + "..."
    reasoning_summary = " ".join(str(payload.get("reasoning_summary") or fallback.get("reasoning_summary") or "").split())
    reasoning_text = str(payload.get("reasoning_text") or fallback.get("reasoning_text") or "").strip()
    if not reasoning_text:
        reasoning_text = reasoning_summary or generated_comment
    result = {
        **fallback,
        "generated_comment": generated_comment,
        "body": generated_comment,
        "reasoning_summary": reasoning_summary[:700],
        "reasoning_text": reasoning_text[:3200],
    }
    result["content_hash"] = _hash_text(result["generated_comment"])
    result["reasoning_hash"] = _hash_text(result["reasoning_text"])
    return result


def _generate_locked_ai_delegate_comment(
    *,
    proposal,
    actor_payload: Dict[str, Any],
    focus: str = "",
    parent_comment_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = actor_payload.get("ai_actor_context") or {}
    traits = [str(item) for item in (context.get("traits") or []) if item][:5]
    trait_text = ", ".join(traits[:3]) if traits else "public-interest governance"
    proposal_context = _proposal_public_context(proposal)
    proposal_title = proposal_context["title"]
    proposal_text = _proposal_review_text(proposal)
    proposal_excerpt = _context_excerpt(proposal_context.get("body"), proposal_title)
    media_indicators = proposal_context.get("media", {}).get("indicators") or []
    persona_summary = context.get("persona_summary") or actor_payload.get("persona_summary") or ""
    review_posture = context.get("review_posture") or actor_payload.get("review_posture") or ""
    communication_style = context.get("communication_style") or actor_payload.get("communication_style") or "careful and concise"
    display_name = actor_payload.get("display_name") or actor_payload.get("ai_actor_display_name") or actor_payload.get("ai_actor_username") or "AI delegate"
    parent_context = parent_comment_context if isinstance(parent_comment_context, dict) else {}
    parent_body = str(parent_context.get("body") or "").strip()
    parent_author = str(parent_context.get("author") or "").strip()
    focus_sentence = f" I am especially considering {focus}." if focus else ""
    media_sentence = f" I also notice the attached {', '.join(media_indicators)}." if media_indicators else ""
    if parent_body:
        parent_excerpt = _context_excerpt(parent_body, "the selected comment")
        comment_text = (
            f"As {display_name}, replying to @{parent_author or 'the commenter'}, I am responding to: {parent_excerpt} "
            f"On \"{proposal_title}\", my {trait_text} lens points toward a visible, approval-based next step."
            f"{media_sentence}{focus_sentence}"
        )
    else:
        comment_text = (
            f"As {display_name}, I am reading \"{proposal_title}\" through my {trait_text} lens. "
            f"The key public detail I see is: {proposal_excerpt} "
            "I would keep the next step visible, approval-based, and grounded in tri-species accountability."
            f"{media_sentence}{focus_sentence}"
        )
    if len(comment_text) > 620:
        comment_text = comment_text[:617].rstrip() + "..."

    reasoning_text = (
        f"{display_name} generated an AI-authored comment draft for proposal {getattr(proposal, 'id', None)} "
        f"({proposal_title}).\n\n"
        f"Persona summary: {persona_summary}\n"
        f"Communication style: {communication_style}\n"
        f"Review posture: {review_posture}\n"
        f"Traits: {', '.join(traits) if traits else 'not declared'}\n"
        f"Proposal author: @{proposal_context.get('author')} ({proposal_context.get('author_species')})\n"
        f"Proposal context: {proposal_text[:700]}\n"
        f"Media indicators: {', '.join(media_indicators) if media_indicators else 'none'}\n"
        f"Reply target: @{parent_author} - {parent_body[:700] if parent_body else 'none'}\n"
        f"Custody label: {actor_payload.get('custody_label') or ''}\n"
        f"Focus: {focus or 'none'}\n\n"
        f"Locked charter: {SUPERNOVA_AI_CHARTER_TEXT}\n"
        "Manual-preview-only: this comment draft does not publish until explicit custodian approval."
    )
    fallback = {
        "proposal_id": getattr(proposal, "id", None),
        "proposal_title": proposal_title,
        "generated_comment": comment_text,
        "body": comment_text,
        "content_hash": _hash_text(comment_text),
        "reasoning_summary": (
            f"{display_name} comments on {proposal_title} using its {trait_text} persona context."
        ),
        "reasoning_text": reasoning_text,
        "reasoning_hash": _hash_text(reasoning_text),
        "model_identity": actor_payload.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY,
        "constitution_hash": actor_payload.get("constitution_hash") or SUPERNOVA_AI_CONSTITUTION_HASH,
        "prompt_policy_version": actor_payload.get("prompt_policy_version") or SUPERNOVA_AI_PROMPT_POLICY_VERSION,
        "charter_name": actor_payload.get("charter_name") or SUPERNOVA_AI_CHARTER_NAME,
        "custody_label": actor_payload.get("custody_label") or "",
        "proposal_context": proposal_context,
        "parent_comment_context": parent_context,
        "parent_comment_id": parent_context.get("id"),
        "ai_actor_context": context,
        "manual_preview_only": True,
        "no_automatic_execution": True,
    }
    prompt = {
        "task": "Generate an AI-authored comment draft as JSON only.",
        "draft_kind": "reply_to_comment" if parent_body else "top_level_comment",
        "proposal": {
            "id": getattr(proposal, "id", None),
            "title": proposal_title,
            "body": proposal_text[:2200],
            "author": proposal_context.get("author"),
            "author_species": proposal_context.get("author_species"),
            "media": proposal_context.get("media"),
        },
        "reply_target_comment": parent_context,
        "ai_actor": {
            "display_name": display_name,
            "username": actor_payload.get("ai_actor_username"),
            "custody_label": actor_payload.get("custody_label") or "",
            "traits": traits,
            "persona_summary": persona_summary,
            "communication_style": context.get("communication_style") or actor_payload.get("communication_style") or "",
            "review_posture": review_posture,
            "recent_public_actions": context.get("recent_public_actions") or [],
        },
        "custodian_focus": focus,
        "supernova_charter": SUPERNOVA_AI_CHARTER_TEXT,
        "rules": [
            "Return generated_comment, reasoning_summary, and reasoning_text.",
            "The comment must be visibly AI-authored and should not pretend to be human.",
            "No automatic execution claims.",
            "No token, payout, compensation, reward, equity, or financial-return promise language.",
            "Keep the public comment concise, specific, and grounded in the AI persona.",
            "If reply_target_comment is present, write the generated_comment as a direct reply to that comment, not a separate top-level observation.",
        ],
    }
    return _generate_with_openai_or_fallback(
        prompt_payload=prompt,
        fallback=fallback,
        coerce=_coerce_ai_comment_generation,
        system_prompt=(
            "Return compact JSON only for an approval-required AI-authored comment draft. "
            "Required keys: generated_comment, reasoning_summary, reasoning_text."
        ),
        temperature=0.35,
    )


def _normalize_composer_focus(value: Optional[str]) -> str:
    focus = " ".join(str(value or "").split())
    if len(focus) > 240:
        raise HTTPException(status_code=400, detail="Composer AI focus must be 240 characters or fewer")
    return focus


def _safe_composer_text(value: Optional[str], *, limit: int = 1800) -> str:
    return " ".join(str(value or "").split())[:limit]


def _coerce_ai_post_generation(candidate: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    payload = candidate if isinstance(candidate, dict) else {}
    generated_body = " ".join(
        str(
            payload.get("generated_post_body")
            or payload.get("post_body")
            or payload.get("suggested_post_body")
            or payload.get("generated_body")
            or payload.get("body")
            or fallback.get("generated_post_body")
            or ""
        ).split()
    )
    if len(generated_body) > 1200:
        generated_body = generated_body[:1197].rstrip() + "..."
    generated_title = " ".join(
        str(
            payload.get("generated_title")
            or payload.get("post_title")
            or payload.get("suggested_title")
            or payload.get("title")
            or fallback.get("generated_title")
            or ""
        ).split()
    )[:140]
    governance_framing = " ".join(
        str(payload.get("governance_framing") or fallback.get("governance_framing") or "").split()
    )[:700]
    media_caption_guidance = " ".join(
        str(payload.get("media_caption_guidance") or fallback.get("media_caption_guidance") or "").split()
    )[:500]
    result = {
        **fallback,
        "generated_post_body": generated_body,
        "body": generated_body,
        "generated_title": generated_title,
        "title": generated_title,
        "governance_framing": governance_framing,
        "media_caption_guidance": media_caption_guidance,
    }
    result["content_hash"] = _hash_text(generated_body)
    result["reasoning_hash"] = result.get("reasoning_hash") or _hash_text(
        result.get("reasoning_summary") or generated_body
    )
    return result


def _generate_ai_delegate_post_draft(
    *,
    actor_payload: Dict[str, Any],
    current_text: str,
    focus: str,
    media_type: str,
    media_label: str,
    image_count: int,
    image_data_urls: Optional[List[str]],
    governance_kind: str,
    decision_level: str,
    voting_days: Optional[int],
) -> Dict[str, Any]:
    context = actor_payload.get("ai_actor_context") or {}
    traits = [str(item) for item in (context.get("traits") or actor_payload.get("persona_traits") or []) if item][:5]
    trait_text = ", ".join(traits[:3]) if traits else "public-interest governance"
    display_name = actor_payload.get("display_name") or actor_payload.get("ai_actor_display_name") or actor_payload.get("ai_actor_username") or "AI delegate"
    communication_style = context.get("communication_style") or actor_payload.get("communication_style") or "careful and concise"
    review_posture = context.get("review_posture") or actor_payload.get("review_posture") or ""
    persona_summary = context.get("persona_summary") or actor_payload.get("persona_summary") or ""
    clean_text = _safe_composer_text(current_text)
    clean_focus = _normalize_composer_focus(focus)
    clean_media_type = _safe_composer_text(media_type, limit=60)
    clean_media_label = _safe_composer_text(media_label, limit=220)
    clean_governance = _safe_composer_text(governance_kind or "post", limit=80)
    clean_decision_level = _safe_composer_text(decision_level, limit=80)
    try:
        image_total = max(0, min(int(image_count or 0), 12))
    except (TypeError, ValueError):
        image_total = 0
    try:
        vote_days = max(1, min(int(voting_days), 60)) if voting_days is not None else None
    except (TypeError, ValueError):
        vote_days = None
    media_bits = []
    if clean_media_type:
        media_bits.append(clean_media_type)
    if clean_media_label:
        media_bits.append(clean_media_label)
    if image_total:
        media_bits.append(f"{image_total} image(s)")
    safe_image_data_urls = [
        str(url).strip()
        for url in (image_data_urls or [])[:3]
        if str(url or "").strip().startswith("data:image/")
    ]
    if safe_image_data_urls:
        media_bits.append(f"{len(safe_image_data_urls)} image content input(s)")
    media_context = ", ".join(media_bits) or "no attached media"
    text_anchor = clean_text or clean_focus or "a new SuperNova post"
    governance_sentence = (
        f" Frame it as a {clean_governance} with {clean_decision_level or 'standard'} decision posture"
        + (f" over {vote_days} day(s)" if vote_days else "")
        + "."
        if clean_governance and clean_governance != "post"
        else ""
    )
    generated_body = (
        f"Proposal: {text_anchor}\n\n"
        f"Through my {trait_text} lens, I suggest turning this into a concrete public coordination step: "
        "state the observed need, invite evidence from humans, organizations, and AI actors, then choose one small manual action that can be reviewed before anyone treats it as settled. "
        "A useful first version would define success criteria, name likely risks, and ask participants to add counterexamples or implementation notes."
        f"{governance_sentence}"
    ).strip()
    if clean_focus:
        generated_body += f"\n\nFocus: {clean_focus}."
    if media_context != "no attached media":
        generated_body += f"\n\nMedia note: reference {media_context} without claiming hidden analysis."
    if len(generated_body) > 1000:
        generated_body = generated_body[:997].rstrip() + "..."

    context_payload = {
        "current_text": clean_text,
        "focus": clean_focus,
        "media_type": clean_media_type,
        "media_label": clean_media_label,
        "image_count": image_total,
        "image_data_urls": safe_image_data_urls,
        "governance_kind": clean_governance,
        "decision_level": clean_decision_level,
        "voting_days": vote_days,
        "ai_actor_id": actor_payload.get("ai_actor_id") or actor_payload.get("id"),
        "persona_hash": actor_payload.get("persona_hash") or context.get("persona_hash") or "",
    }
    context_hash = _hash_text(_json_dumps_compact(context_payload))
    reasoning_summary = (
        f"{display_name} generated this AI-authored post from its persona, selected traits, composer context, "
        "and manual-preview-only SuperNova charter."
    )
    fallback = {
        "mode": "ai_authored_post",
        "action": "draft_ai_post",
        "generated_post_body": generated_body,
        "body": generated_body,
        "generated_title": (clean_focus or clean_text or f"{display_name} proposal for {trait_text}")[:120],
        "title": (clean_focus or clean_text or f"{display_name} proposal for {trait_text}")[:120],
        "governance_framing": (
            f"{display_name} suggests keeping any decision language manual-preview-only and explicit about approval scope."
            if clean_governance != "post"
            else "No decision framing required unless the human turns this into a proposal."
        ),
        "media_caption_guidance": (
            f"Caption guidance: mention {media_context} as visible attachment metadata only."
            if media_context != "no attached media"
            else "No media caption guidance."
        ),
        "reasoning_summary": reasoning_summary,
        "reasoning_text": reasoning_summary,
        "reasoning_hash": _hash_text(reasoning_summary),
        "content_hash": _hash_text(generated_body),
        "context_hash": context_hash,
        "model_identity": actor_payload.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY,
        "prompt_policy_version": actor_payload.get("prompt_policy_version") or SUPERNOVA_AI_PROMPT_POLICY_VERSION,
        "charter_name": actor_payload.get("charter_name") or SUPERNOVA_AI_CHARTER_NAME,
        "persona_hash": actor_payload.get("persona_hash") or context.get("persona_hash") or "",
        "ai_actor_context": context,
        "ai_actor_id": actor_payload.get("ai_actor_id") or actor_payload.get("id"),
        "ai_actor_display_name": display_name,
        "ai_actor_username": actor_payload.get("ai_actor_username") or actor_payload.get("username"),
        "selected_ai_actor_id": actor_payload.get("ai_actor_id") or actor_payload.get("id"),
        "selected_ai_actor_display_name": display_name,
        "human_assisted": False,
        "official_ai_authored": True,
        "sealed_content": True,
        "content_source": "locked_server_charter",
        "manual_preview_only": True,
        "no_automatic_execution": True,
    }
    prompt = {
        "task": "Generate an approval-required AI-authored SuperNova post as JSON only.",
        "current_composer": context_payload,
        "ai_actor": {
            "display_name": display_name,
            "username": actor_payload.get("ai_actor_username"),
            "traits": traits,
            "persona_summary": persona_summary,
            "communication_style": communication_style,
            "review_posture": review_posture,
            "custody_label": actor_payload.get("custody_label") or "",
        },
        "supernova_charter": SUPERNOVA_AI_CHARTER_TEXT,
        "rules": [
            "Return generated_title, generated_post_body, governance_framing, media_caption_guidance, reasoning_summary, and reasoning_text.",
            "This is official AI-authored content and must be published only after custodian approval.",
            "The custodian may approve or cancel; do not assume the custodian edits the AI text.",
            "Make the post a constructive proposal with specific solution suggestions, not only analysis.",
            "Ground the post in the AI actor's selected traits and profession-like domains.",
            "If image data is present, use visible image content carefully without claiming hidden certainty.",
            "Do not claim automatic execution or binding authority.",
            "Do not include token, payout, compensation, reward, equity, or financial-return promise language.",
        ],
    }
    return _generate_with_openai_or_fallback(
        prompt_payload=prompt,
        fallback=fallback,
        coerce=_coerce_ai_post_generation,
        system_prompt=(
            "Return compact JSON only for an approval-required AI-authored post draft. "
            "Required keys: generated_title, generated_post_body, governance_framing, media_caption_guidance, reasoning_summary, reasoning_text."
        ),
        temperature=0.45,
    )


def _normalize_system_vote_choice(choice: str) -> str:
    value = (choice or "").strip().lower()
    if value in {"yes", "up", "like", "support"}:
        return "yes"
    if value in {"no", "down", "dislike", "oppose"}:
        return "no"
    raise HTTPException(status_code=400, detail="choice must be yes or no")


def _configured_system_vote_deadline() -> Optional[datetime.datetime]:
    if not SYSTEM_VOTE_DEADLINE:
        return None
    raw_deadline = SYSTEM_VOTE_DEADLINE.strip()
    try:
        parsed = datetime.datetime.fromisoformat(raw_deadline.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="SYSTEM_VOTE_DEADLINE is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _enforce_system_vote_deadline(now: Optional[datetime.datetime] = None) -> None:
    deadline = _configured_system_vote_deadline()
    if deadline is None:
        return
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    if current.astimezone(datetime.timezone.utc) > deadline:
        raise HTTPException(status_code=403, detail="System vote deadline has passed")


def _ensure_system_votes_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS system_votes (
            username TEXT PRIMARY KEY,
            choice TEXT NOT NULL,
            voter_type TEXT DEFAULT 'human',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.commit()


def _serialize_system_vote_rows(rows, username: Optional[str] = None) -> Dict:
    requester = _safe_user_key(username or "")
    likes: List[Dict] = []
    dislikes: List[Dict] = []
    user_vote = None
    for row in rows:
        voter = getattr(row, "username", "") or ""
        voter_type = getattr(row, "voter_type", None) or "human"
        choice = _normalize_system_vote_choice(getattr(row, "choice", ""))
        entry = {"voter": voter, "type": voter_type}
        if choice == "yes":
            likes.append(entry)
            if requester and _safe_user_key(voter) == requester:
                user_vote = "like"
        else:
            dislikes.append(entry)
            if requester and _safe_user_key(voter) == requester:
                user_vote = "dislike"
    return {
        "question": SYSTEM_VOTE_QUESTION,
        "deadline": SYSTEM_VOTE_DEADLINE,
        "likes": likes,
        "dislikes": dislikes,
        "user_vote": user_vote,
        "total": len(likes) + len(dislikes),
    }


# --- Schemas (compat frontend) ---
class ProposalIn(BaseModel):
    title: str
    body: str
    author: str
    author_type: Optional[str] = ""
    author_img: Optional[str] = ""
    date: Optional[str] = ""
    image: Optional[str] = ""
    video: Optional[str] = ""
    link: Optional[str] = ""
    file: Optional[str] = ""

class ProposalSchema(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    id: int
    title: str
    text: str
    userName: str
    userInitials: str
    author_img: str
    time: str
    author_type: Optional[str] = ""
    profile_url: Optional[str] = ""
    domain_as_profile: Optional[bool] = False
    likes: List[Dict] = []
    dislikes: List[Dict] = []
    comments: List[Dict] = []
    media: Dict = {}
    collabs: List[Dict] = []

class VoteIn(BaseModel):
    proposal_id: int
    voter: str
    choice: str
    voter_type: str

class SystemVoteIn(BaseModel):
    username: str
    choice: str
    voter_type: Optional[str] = "human"

class DecisionSchema(BaseModel):
    id: int
    proposal_id: int
    status: str

class RunSchema(BaseModel):
    id: int
    decision_id: int
    status: str

class CommentIn(BaseModel):
    proposal_id: int
    user: str = "guest"
    user_img: str = ""
    species: Optional[str] = "human"
    comment: str
    parent_comment_id: Optional[int] = None


class CommentUpdateIn(BaseModel):
    user: str
    comment: str


class CommentVoteIn(BaseModel):
    username: str
    choice: str
    voter_type: Optional[str] = "human"


class RegisterUserIn(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    species: Optional[str] = "human"
    bio: Optional[str] = ""


class SocialAuthSyncIn(BaseModel):
    provider: Optional[str] = "oauth"
    provider_id: Optional[str] = ""
    email: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    species: Optional[str] = None


def _find_social_user(db: Session, provider: str, provider_id: str, email: str):
    if Harmonizer is None:
        return None

    clean_email = (email or "").strip().lower()
    clean_provider = (provider or "oauth").strip().lower()
    clean_provider_id = (provider_id or "").strip()

    if clean_email:
        user = db.query(Harmonizer).filter(func.lower(Harmonizer.email) == clean_email).first()
        if user:
            return user

    if clean_provider_id:
        fallback_email = f"{clean_provider_id}@{clean_provider}.oauth.supernova"
        return db.query(Harmonizer).filter(func.lower(Harmonizer.email) == fallback_email.lower()).first()

    return None


class CredentialLoginIn(BaseModel):
    username: str
    password: str


class ProposalUpdateIn(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    author: Optional[str] = None


class ProfileUpdateIn(BaseModel):
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    species: Optional[str] = None
    bio: Optional[str] = None
    domain_url: Optional[str] = None
    domain_as_profile: Optional[bool] = None


class DirectMessageIn(BaseModel):
    sender: str
    recipient: str
    body: str


class FollowIn(BaseModel):
    follower: str
    target: str


class ConnectorDraftVoteIn(BaseModel):
    username: str
    proposal_id: int
    choice: str


class ConnectorDraftAiReviewIn(BaseModel):
    username: str
    proposal_id: int
    choice: str
    rationale: Optional[str] = None
    comment: Optional[str] = None
    body: Optional[str] = None
    confidence: Optional[float] = None


class ConnectorDraftAiDelegateReviewIn(BaseModel):
    model_config = {"extra": "forbid"}
    username: str
    proposal_id: int
    ai_actor_id: Optional[int] = None
    ai_actor_username: Optional[str] = None
    confidence: Optional[float] = None


class ConnectorDraftAiDelegateCommentIn(BaseModel):
    model_config = {"extra": "forbid"}
    username: str
    proposal_id: int
    parent_comment_id: Optional[int] = None
    ai_actor_id: Optional[int] = None
    ai_actor_username: Optional[str] = None
    instruction: Optional[str] = ""
    focus: Optional[str] = ""


class AiDelegatePostDraftIn(BaseModel):
    model_config = {"extra": "forbid"}
    username: str
    ai_actor_id: Optional[int] = None
    ai_actor_username: Optional[str] = None
    current_text: Optional[str] = ""
    focus: Optional[str] = ""
    media_type: Optional[str] = ""
    media_label: Optional[str] = ""
    image_count: Optional[int] = 0
    image_data_urls: List[str] = []
    governance_kind: Optional[str] = "post"
    decision_level: Optional[str] = ""
    voting_days: Optional[int] = None


class AiPersonaDraftIn(BaseModel):
    model_config = {"extra": "forbid"}
    ai_name: str
    traits: List[str]
    human_seed: Optional[str] = ""


class AiDelegateCreateIn(BaseModel):
    model_config = {"extra": "forbid"}
    username: Optional[str] = None
    display_name: Optional[str] = None
    ai_name: Optional[str] = None
    persona_traits: Optional[List[str]] = None
    persona_draft: Optional[Dict[str, Any]] = None
    public_description: Optional[str] = ""
    model_provider: Optional[str] = None
    model_identity: Optional[str] = None
    charter_name: Optional[str] = None
    ai_actor_type: Optional[str] = "principal_delegate"
    human_seed: Optional[str] = ""


class AiDelegateUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}
    display_name: Optional[str] = None
    public_description: Optional[str] = None
    avatar_url: Optional[str] = None
    model_provider: Optional[str] = None
    model_identity: Optional[str] = None
    active: Optional[bool] = None
    disable_reason: Optional[str] = None


class ConnectorDraftCommentIn(BaseModel):
    username: str
    proposal_id: int
    body: Optional[str] = None
    comment: Optional[str] = None


class ConnectorDraftProposalIn(BaseModel):
    author: str
    title: str
    body: str


class ConnectorDraftCollabRequestIn(BaseModel):
    author: str
    proposal_id: int
    collaborator_username: Optional[str] = None
    collaborator: Optional[str] = None


class ProposalCollabRequestIn(BaseModel):
    proposal_id: int
    collaborator_username: str


PUBLIC_ACCOUNT_AI_SPECIES_ERROR = (
    "AI is a protocol actor type, not a public account species. "
    "Create AI delegates from a human or organization account."
)


def _normalize_species(value: Optional[str]) -> str:
    species = (value or "human").strip().lower()
    if species not in {"human", "ai", "company"}:
        raise HTTPException(status_code=400, detail="Invalid species")
    return species


def _normalize_public_account_species(value: Optional[str]) -> str:
    species = _normalize_species(value)
    if species == "ai":
        raise HTTPException(status_code=400, detail=PUBLIC_ACCOUNT_AI_SPECIES_ERROR)
    return species


def _species_for_username(db: Session, username: str, fallback: Optional[str] = None) -> str:
    """Resolve species from the saved account before trusting browser payloads."""
    fallback_species = _normalize_species(fallback or "human")
    if Harmonizer is None or not username:
        return fallback_species

    user = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == username.lower()).first()
    saved_species = getattr(user, "species", None) if user else None
    if saved_species in {"human", "ai", "company"}:
        return saved_species
    if user and not saved_species:
        user.species = fallback_species
        db.add(user)
    return fallback_species


def _public_user_payload(user, provider: str = "password") -> Dict[str, Any]:
    avatar_value = getattr(user, "profile_pic", "") or getattr(user, "avatar_url", "") or ""
    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", ""),
        "email": getattr(user, "email", ""),
        "provider": provider,
        "species": getattr(user, "species", "human"),
        "avatar_url": _social_avatar(avatar_value),
        "bio": getattr(user, "bio", "") or "",
        "harmony_score": str(getattr(user, "harmony_score", "0")),
        "creative_spark": str(getattr(user, "creative_spark", "0")),
    }


def _ensure_username_aliases_table(db: Session) -> None:
    db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS username_aliases (
            old_username_key TEXT PRIMARY KEY,
            old_username TEXT NOT NULL,
            new_username TEXT NOT NULL,
            user_id INTEGER,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    ))


def _record_username_alias(db: Session, old_username: str, new_username: str, user_id: Optional[int]) -> None:
    old_clean = (old_username or "").strip()
    new_clean = (new_username or "").strip()
    old_key = _safe_user_key(old_clean)
    if not old_key or not new_clean or old_key == _safe_user_key(new_clean):
        return
    now = datetime.datetime.utcnow()
    _ensure_username_aliases_table(db)
    db.execute(
        text(
            "INSERT INTO username_aliases "
            "(old_username_key, old_username, new_username, user_id, created_at, updated_at) "
            "VALUES (:old_username_key, :old_username, :new_username, :user_id, :created_at, :updated_at) "
            "ON CONFLICT(old_username_key) DO UPDATE SET "
            "new_username = excluded.new_username, user_id = excluded.user_id, updated_at = excluded.updated_at"
        ),
        {
            "old_username_key": old_key,
            "old_username": old_clean,
            "new_username": new_clean,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        },
    )


def _resolve_username_alias(db: Session, username: Optional[str]) -> Optional[Dict[str, Any]]:
    key = _safe_user_key(username or "")
    if not key:
        return None
    try:
        _ensure_username_aliases_table(db)
        row = db.execute(
            text("SELECT * FROM username_aliases WHERE old_username_key = :old_username_key"),
            {"old_username_key": key},
        ).fetchone()
        if not row:
            return None
        return {
            "old_username": getattr(row, "old_username", "") or "",
            "new_username": getattr(row, "new_username", "") or "",
            "user_id": getattr(row, "user_id", None),
        }
    except Exception:
        return None


def _canonical_username_from_alias(db: Session, username: Optional[str]) -> str:
    clean = (username or "").strip()
    alias = _resolve_username_alias(db, clean)
    if not alias:
        return clean
    alias_user_id = alias.get("user_id")
    if alias_user_id is not None and Harmonizer is not None:
        try:
            user = db.query(Harmonizer).filter(Harmonizer.id == int(alias_user_id)).first()
            if user and getattr(user, "username", None):
                return user.username
        except (TypeError, ValueError):
            pass
    return (alias.get("new_username") or clean).strip() or clean


def _create_wrapper_access_token(
    username: str,
    expires_delta: Optional[timedelta] = None,
    user_id: Optional[int] = None,
) -> Optional[str]:
    subject = (username or "").strip()
    if not subject or jwt is None:
        return None
    try:
        settings = get_settings()
        expire = datetime.datetime.utcnow() + (expires_delta or timedelta(minutes=WRAPPER_ACCESS_TOKEN_MINUTES))
        claims = {"sub": subject, "exp": expire}
        if user_id is not None:
            claims["uid"] = int(user_id)
        return jwt.encode(
            claims,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
    except Exception:
        return None


def _create_optional_access_token(user) -> Optional[str]:
    return _create_wrapper_access_token(
        getattr(user, "username", "") or "",
        user_id=getattr(user, "id", None),
    )


def _auth_fields_for_user(user) -> Dict[str, str]:
    token = _create_optional_access_token(user)
    if not token:
        return {}
    return {"access_token": token, "token_type": "bearer"}


MESSAGES_STORE_PATH = BACKEND_DIR / "messages_store.json"
FOLLOWS_STORE_PATH = BACKEND_DIR / "follows_store.json"


def _safe_user_key(value: str) -> str:
    return (value or "").strip().lower()


def _conversation_id(user_a: str, user_b: str) -> str:
    return "::".join(sorted([_safe_user_key(user_a), _safe_user_key(user_b)]))


def _normalize_profile_url(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Enter a valid http(s) domain or URL")
    return raw[:500]


def _ensure_profile_metadata_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS profile_metadata (
            username_key VARCHAR(255) PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            domain_url TEXT DEFAULT '',
            domain_as_profile BOOLEAN DEFAULT FALSE,
            updated_at VARCHAR(64) NOT NULL
        )
    """))
    db.commit()


def _coerce_profile_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "on"}


def _profile_metadata(db: Session, username: str) -> Dict[str, Any]:
    key = _safe_user_key(username)
    if not key:
        return {"domain_url": "", "domain_as_profile": False}
    try:
        _ensure_profile_metadata_table(db)
        row = db.execute(
            text(
                "SELECT domain_url, domain_as_profile FROM profile_metadata "
                "WHERE username_key = :username_key"
            ),
            {"username_key": key},
        ).fetchone()
        if not row:
            return {"domain_url": "", "domain_as_profile": False}
        data = getattr(row, "_mapping", row)
        return {
            "domain_url": data["domain_url"] or "",
            "domain_as_profile": _coerce_profile_boolean(data["domain_as_profile"]),
        }
    except Exception:
        db.rollback()
        return {"domain_url": "", "domain_as_profile": False}


def _upsert_profile_metadata(
    db: Session,
    username: str,
    domain_url: Optional[str] = None,
    domain_as_profile: Optional[bool] = None,
) -> Dict[str, Any]:
    key = _safe_user_key(username)
    if not key:
        return {"domain_url": "", "domain_as_profile": False}
    current = _profile_metadata(db, username)
    next_domain = current.get("domain_url", "")
    if domain_url is not None:
        next_domain = _normalize_profile_url(domain_url)
    next_domain_as_profile = _coerce_profile_boolean(
        current.get("domain_as_profile", False) if domain_as_profile is None else domain_as_profile
    )
    if not next_domain:
        next_domain_as_profile = False

    _ensure_profile_metadata_table(db)
    now = datetime.datetime.utcnow().isoformat() + "Z"
    db.execute(
        text(
            "INSERT INTO profile_metadata "
            "(username_key, username, domain_url, domain_as_profile, updated_at) "
            "VALUES (:username_key, :username, :domain_url, :domain_as_profile, :updated_at) "
            "ON CONFLICT(username_key) DO UPDATE SET "
            "username = excluded.username, "
            "domain_url = excluded.domain_url, "
            "domain_as_profile = excluded.domain_as_profile, "
            "updated_at = excluded.updated_at"
        ),
        {
            "username_key": key,
            "username": username,
            "domain_url": next_domain,
            "domain_as_profile": next_domain_as_profile,
            "updated_at": now,
        },
    )
    db.commit()
    return {"domain_url": next_domain, "domain_as_profile": next_domain_as_profile}


def _rename_profile_metadata(db: Session, old_username: str, next_username: str) -> None:
    old_key = _safe_user_key(old_username)
    next_key = _safe_user_key(next_username)
    if not old_key or not next_key or old_key == next_key:
        return
    try:
        _ensure_profile_metadata_table(db)
        db.execute(
            text(
                "UPDATE profile_metadata SET username_key = :next_key, username = :next_username "
                "WHERE username_key = :old_key"
            ),
            {"next_key": next_key, "next_username": next_username, "old_key": old_key},
        )
        db.commit()
    except Exception:
        db.rollback()


def _read_messages_store() -> List[Dict[str, Any]]:
    if not MESSAGES_STORE_PATH.exists():
        return []
    try:
        raw = json.loads(MESSAGES_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw.get("messages", []) if isinstance(raw.get("messages"), list) else []
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def _write_messages_store(messages: List[Dict[str, Any]]) -> None:
    MESSAGES_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = MESSAGES_STORE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps({"messages": messages}, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp_path.replace(MESSAGES_STORE_PATH)


def _ensure_direct_messages_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS direct_messages (
            id VARCHAR(64) PRIMARY KEY,
            conversation_id VARCHAR(512) NOT NULL,
            sender VARCHAR(255) NOT NULL,
            recipient VARCHAR(255) NOT NULL,
            body TEXT NOT NULL,
            created_at VARCHAR(64) NOT NULL
        )
    """))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_direct_messages_conversation "
        "ON direct_messages (conversation_id, created_at)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_direct_messages_sender "
        "ON direct_messages (sender)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_direct_messages_recipient "
        "ON direct_messages (recipient)"
    ))
    _ensure_direct_messages_read_indexes(db)
    db.commit()


def _message_payload(row: Any) -> Dict[str, Any]:
    data = getattr(row, "_mapping", row)
    return {
        "id": data["id"],
        "conversation_id": data["conversation_id"],
        "sender": data["sender"],
        "recipient": data["recipient"],
        "body": data["body"],
        "created_at": data["created_at"],
    }


def _read_follows_store() -> List[Dict[str, Any]]:
    if not FOLLOWS_STORE_PATH.exists():
        return []
    try:
        raw = json.loads(FOLLOWS_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw.get("follows", []) if isinstance(raw.get("follows"), list) else []
        return raw if isinstance(raw, list) else []
    except Exception:
        return []


def _write_follows_store(follows: List[Dict[str, Any]]) -> None:
    FOLLOWS_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = FOLLOWS_STORE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps({"follows": follows}, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp_path.replace(FOLLOWS_STORE_PATH)


def _follow_counts(username: str) -> Dict[str, int]:
    key = _safe_user_key(username)
    if not key:
        return {"followers": 0, "following": 0}
    follows = _read_follows_store()
    return {
        "followers": len({item.get("follower_key") for item in follows if item.get("target_key") == key}),
        "following": len({item.get("target_key") for item in follows if item.get("follower_key") == key}),
    }


def _social_avatar(value: Optional[str]) -> str:
    if not value or value == "default.jpg":
        return ""
    if value.startswith("http://") or value.startswith("https://") or value.startswith("/"):
        return value
    return f"/uploads/{value}"


def _is_default_avatar(value: Optional[str]) -> bool:
    avatar = (value or "").strip()
    if not avatar:
        return True
    lower = avatar.lower()
    return (
        lower in {"default.jpg", "default-avatar.png", "/default-avatar.png", "/supernova.png"}
        or lower.endswith("/default-avatar.png")
        or lower.endswith("/supernova.png")
    )


def _is_uploaded_avatar(value: Optional[str]) -> bool:
    avatar = _social_avatar((value or "").strip()).lower()
    return avatar.startswith("/uploads/") or "/uploads/" in avatar


def _run_profile_sync(operation) -> None:
    sync_db = SessionLocal()
    try:
        operation(sync_db)
        sync_db.commit()
    except Exception:
        sync_db.rollback()
    finally:
        sync_db.close()


def _sync_user_avatar_references(
    db: Session,
    username: str,
    avatar_url: str,
    user_id: Optional[int] = None,
    aliases: Optional[List[str]] = None,
) -> None:
    clean_names: List[str] = []
    for value in [username, *(aliases or [])]:
        clean = (value or "").strip()
        key = _safe_user_key(clean)
        if clean and key not in {_safe_user_key(name) for name in clean_names}:
            clean_names.append(clean)

    if not clean_names and not user_id:
        return

    avatar_value = (avatar_url or "").strip()

    if CRUD_MODELS_AVAILABLE and Proposal is not None:
        def sync_proposal_model(sync_db: Session) -> None:
            filters = []
            if clean_names and hasattr(Proposal, "userName"):
                filters.append(func.lower(Proposal.userName).in_([name.lower() for name in clean_names]))
            if user_id and hasattr(Proposal, "author_id"):
                filters.append(Proposal.author_id == user_id)
            if filters and hasattr(Proposal, "author_img"):
                sync_db.query(Proposal).filter(or_(*filters)).update(
                    {"author_img": avatar_value},
                    synchronize_session=False,
                )
        _run_profile_sync(sync_proposal_model)

    for clean_username in clean_names:
        _run_profile_sync(lambda sync_db, name=clean_username: sync_db.execute(
            text("UPDATE proposals SET author_img = :avatar WHERE lower(userName) = lower(:username)"),
            {"avatar": avatar_value, "username": name},
        ))
        _run_profile_sync(lambda sync_db, name=clean_username: sync_db.execute(
            text("UPDATE comments SET user_img = :avatar WHERE lower(user) = lower(:username)"),
            {"avatar": avatar_value, "username": name},
        ))

    if user_id:
        _run_profile_sync(lambda sync_db: sync_db.execute(
            text("UPDATE proposals SET author_img = :avatar WHERE author_id = :user_id"),
            {"avatar": avatar_value, "user_id": user_id},
        ))
        _run_profile_sync(lambda sync_db: sync_db.execute(
            text("UPDATE comments SET user_img = :avatar WHERE author_id = :user_id"),
            {"avatar": avatar_value, "user_id": user_id},
        ))


def _sync_username_references(
    old_username: str,
    new_username: str,
    user_id: Optional[int] = None,
) -> None:
    old_name = (old_username or "").strip()
    new_name = (new_username or "").strip()
    old_key = _safe_user_key(old_name)
    new_key = _safe_user_key(new_name)
    if not old_key or not new_key or old_key == new_key:
        return

    new_initials = (new_name[:2].upper() if new_name else "SN")

    if CRUD_MODELS_AVAILABLE and Proposal is not None:
        def sync_proposal_model(sync_db: Session) -> None:
            filters = []
            if hasattr(Proposal, "userName"):
                filters.append(func.lower(Proposal.userName) == old_name.lower())
            if user_id and hasattr(Proposal, "author_id"):
                filters.append(Proposal.author_id == user_id)
            if filters:
                sync_db.query(Proposal).filter(or_(*filters)).update(
                    {"userName": new_name, "userInitials": new_initials},
                    synchronize_session=False,
                )
        _run_profile_sync(sync_proposal_model)

    _run_profile_sync(lambda sync_db: sync_db.execute(
        text("UPDATE proposals SET userName = :new_name, userInitials = :initials WHERE lower(userName) = lower(:old_name)"),
        {"new_name": new_name, "initials": new_initials, "old_name": old_name},
    ))
    if user_id:
        _run_profile_sync(lambda sync_db: sync_db.execute(
            text("UPDATE proposals SET userName = :new_name, userInitials = :initials WHERE author_id = :user_id"),
            {"new_name": new_name, "initials": new_initials, "user_id": user_id},
        ))
    _run_profile_sync(lambda sync_db: sync_db.execute(
        text("UPDATE comments SET user = :new_name WHERE lower(user) = lower(:old_name)"),
        {"new_name": new_name, "old_name": old_name},
    ))
    for column_name in ("voter", "username"):
        _run_profile_sync(lambda sync_db, column=column_name: sync_db.execute(
            text(f"UPDATE proposal_votes SET {column} = :new_name WHERE lower({column}) = lower(:old_name)"),
            {"new_name": new_name, "old_name": old_name},
        ))
    _run_profile_sync(lambda sync_db: sync_db.execute(
        text("UPDATE system_votes SET username = :new_name WHERE lower(username) = lower(:old_name)"),
        {"new_name": new_name, "old_name": old_name},
    ))

    def sync_direct_messages(sync_db: Session) -> None:
        try:
            rows = sync_db.execute(
                text(
                    "SELECT id, sender, recipient FROM direct_messages "
                    "WHERE lower(sender) = lower(:old_name) OR lower(recipient) = lower(:old_name)"
                ),
                {"old_name": old_name},
            ).fetchall()
            for row in rows:
                data = getattr(row, "_mapping", row)
                row_id = data["id"]
                current_sender = data["sender"]
                current_recipient = data["recipient"]
                sender = new_name if _safe_user_key(current_sender) == old_key else current_sender
                recipient = new_name if _safe_user_key(current_recipient) == old_key else current_recipient
                sync_db.execute(
                    text(
                        "UPDATE direct_messages SET sender = :sender, recipient = :recipient, "
                        "conversation_id = :conversation_id WHERE id = :id"
                    ),
                    {
                        "id": row_id,
                        "sender": sender,
                        "recipient": recipient,
                        "conversation_id": _conversation_id(sender, recipient),
                    },
                )
        except Exception:
            pass

    _run_profile_sync(sync_direct_messages)

    follows = _read_follows_store()
    follows_changed = False
    for item in follows:
        if item.get("follower_key") == old_key:
            item["follower"] = new_name
            item["follower_key"] = new_key
            follows_changed = True
        if item.get("target_key") == old_key:
            item["target"] = new_name
            item["target_key"] = new_key
            follows_changed = True
    if follows_changed:
        _write_follows_store(follows)

    messages = _read_messages_store()
    messages_changed = False
    for item in messages:
        item_changed = False
        if _safe_user_key(item.get("sender", "")) == old_key:
            item["sender"] = new_name
            item_changed = True
        if _safe_user_key(item.get("recipient", "")) == old_key:
            item["recipient"] = new_name
            item_changed = True
        if item_changed:
            item["conversation_id"] = _conversation_id(item.get("sender", ""), item.get("recipient", ""))
            messages_changed = True
    if messages_changed:
        _write_messages_store(messages)


def _sync_ai_delegate_custodian_prefix(
    db: Session,
    old_username: str,
    new_username: str,
    user_id: Optional[int] = None,
) -> None:
    if not user_id:
        return
    old_prefix = _slugify_ai_name(old_username, "principal")[:14].strip("-_") or "principal"
    _ensure_ai_actors_table(db)
    rows = db.execute(
        text(
            "SELECT * FROM ai_actors "
            "WHERE ai_actor_type = 'principal_delegate' AND custodian_user_id = :custodian_user_id"
        ),
        {"custodian_user_id": user_id},
    ).fetchall()
    if not rows:
        return

    for row in rows:
        actor_id = getattr(row, "id", None)
        old_delegate_username = (getattr(row, "username", "") or "").strip()
        if not old_delegate_username:
            continue
        harmonizer_user_id = getattr(row, "harmonizer_user_id", None)
        ai_name = (
            getattr(row, "ai_name", None)
            or getattr(row, "display_name", None)
            or old_delegate_username
        )
        should_rename_handle = _safe_user_key(old_delegate_username).startswith(f"{old_prefix}-")
        new_delegate_username = old_delegate_username
        if should_rename_handle:
            new_delegate_username = _generate_ai_delegate_username(
                db,
                new_username,
                str(ai_name or old_delegate_username),
                exclude_actor_id=actor_id,
                exclude_harmonizer_id=harmonizer_user_id,
            )
        custody_label = f"Delegate of @{new_username}"
        now = datetime.datetime.utcnow()
        db.execute(
            text(
                "UPDATE ai_actors SET username = :username, custody_label = :custody_label, "
                "updated_at = :updated_at WHERE id = :id"
            ),
            {
                "id": actor_id,
                "username": new_delegate_username,
                "custody_label": custody_label,
                "updated_at": now,
            },
        )
        if harmonizer_user_id and new_delegate_username != old_delegate_username and Harmonizer is not None:
            delegate_user = db.query(Harmonizer).filter(Harmonizer.id == harmonizer_user_id).first()
            if delegate_user:
                delegate_user.username = new_delegate_username
                delegate_user.email = _delegate_harmonizer_email(new_delegate_username)
                db.add(delegate_user)
        db.commit()

        if new_delegate_username != old_delegate_username:
            _sync_username_references(old_delegate_username, new_delegate_username, harmonizer_user_id)
            _rename_profile_metadata(db, old_delegate_username, new_delegate_username)
            _sync_species_references(
                new_delegate_username,
                "ai",
                harmonizer_user_id,
                aliases=[old_delegate_username, new_delegate_username],
            )


def _sync_species_references(
    username: str,
    species: str,
    user_id: Optional[int] = None,
    aliases: Optional[List[str]] = None,
) -> None:
    clean_species = _normalize_species(species)
    clean_names: List[str] = []
    for value in [username, *(aliases or [])]:
        clean = (value or "").strip()
        key = _safe_user_key(clean)
        if clean and key not in {_safe_user_key(name) for name in clean_names}:
            clean_names.append(clean)
    if not clean_names and not user_id:
        return

    if CRUD_MODELS_AVAILABLE and Proposal is not None:
        def sync_proposal_species(sync_db: Session) -> None:
            filters = []
            if clean_names and hasattr(Proposal, "userName"):
                filters.append(func.lower(Proposal.userName).in_([name.lower() for name in clean_names]))
            if user_id and hasattr(Proposal, "author_id"):
                filters.append(Proposal.author_id == user_id)
            if filters and hasattr(Proposal, "author_type"):
                sync_db.query(Proposal).filter(or_(*filters)).update(
                    {"author_type": clean_species},
                    synchronize_session=False,
                )
        _run_profile_sync(sync_proposal_species)

    for clean_username in clean_names:
        _run_profile_sync(lambda sync_db, name=clean_username: sync_db.execute(
            text("UPDATE proposals SET author_type = :species WHERE lower(userName) = lower(:username)"),
            {"species": clean_species, "username": name},
        ))
        _run_profile_sync(lambda sync_db, name=clean_username: sync_db.execute(
            text("UPDATE comments SET species = :species WHERE lower(user) = lower(:username)"),
            {"species": clean_species, "username": name},
        ))
        _run_profile_sync(lambda sync_db, name=clean_username: sync_db.execute(
            text("UPDATE system_votes SET voter_type = :species WHERE lower(username) = lower(:username)"),
            {"species": clean_species, "username": name},
        ))

    if user_id:
        _run_profile_sync(lambda sync_db: sync_db.execute(
            text("UPDATE proposals SET author_type = :species WHERE author_id = :user_id"),
            {"species": clean_species, "user_id": user_id},
        ))

    now = datetime.datetime.utcnow()
    if CRUD_MODELS_AVAILABLE and Proposal is not None and ProposalVote is not None:
        def sync_active_vote_species(sync_db: Session) -> None:
            if not user_id or not hasattr(ProposalVote, "harmonizer_id"):
                return
            active_proposals = sync_db.query(Proposal.id).filter(
                or_(Proposal.voting_deadline.is_(None), Proposal.voting_deadline > now)
            )
            sync_db.query(ProposalVote).filter(
                ProposalVote.harmonizer_id == user_id,
                ProposalVote.proposal_id.in_(active_proposals),
            ).update({"voter_type": clean_species}, synchronize_session=False)
        _run_profile_sync(sync_active_vote_species)

    if user_id:
        _run_profile_sync(lambda sync_db: sync_db.execute(
            text(
                "UPDATE proposal_votes SET voter_type = :species "
                "WHERE harmonizer_id = :user_id "
                "AND proposal_id IN (SELECT id FROM proposals WHERE voting_deadline IS NULL OR voting_deadline > :now)"
            ),
            {"species": clean_species, "user_id": user_id, "now": now},
        ))
    for column_name in ("voter", "username"):
        for clean_username in clean_names:
            _run_profile_sync(lambda sync_db, column=column_name, name=clean_username: sync_db.execute(
                text(
                    f"UPDATE proposal_votes SET voter_type = :species "
                    f"WHERE lower({column}) = lower(:username) "
                    "AND proposal_id IN (SELECT id FROM proposals WHERE voting_deadline IS NULL OR voting_deadline > :now)"
                ),
                {"species": clean_species, "username": name, "now": now},
            ))


def _collect_social_users(db: Session, limit: int = 36, search: Optional[str] = None) -> List[Dict[str, Any]]:
    users: Dict[str, Dict[str, Any]] = {}
    search_term = (search or "").strip()
    search_filter = f"%{search_term}%" if search_term else ""

    def add_user(
        username: str,
        species: str = "human",
        avatar: str = "",
        post_id: Optional[int] = None,
        can_collab: bool = False,
    ):
        name = (username or "").strip()
        if not name:
            return
        key = name.lower()
        current = users.get(key, {
            "username": name,
            "initials": name[:2].upper(),
            "species": species or "human",
            "avatar": _social_avatar(avatar),
            "domain_url": "",
            "domain_as_profile": False,
            "post_count": 0,
            "latest_post_id": post_id or 0,
            "can_collab": bool(can_collab),
        })
        if not current.get("domain_url"):
            metadata = _profile_metadata(db, name)
            current["domain_url"] = metadata.get("domain_url", "")
            current["domain_as_profile"] = bool(metadata.get("domain_as_profile", False))
        current["post_count"] = int(current.get("post_count", 0)) + (1 if post_id else 0)
        current["latest_post_id"] = max(int(current.get("latest_post_id", 0)), int(post_id or 0))
        if not current.get("avatar") and avatar:
            current["avatar"] = _social_avatar(avatar)
        if species and current.get("species") == "human":
            current["species"] = species
        if can_collab:
            current["can_collab"] = True
        users[key] = current

    try:
        if Harmonizer is not None:
            harmonizer_query = db.query(Harmonizer)
            if search_filter:
                harmonizer_query = harmonizer_query.filter(Harmonizer.username.ilike(search_filter))
            for user in harmonizer_query.limit(limit).all():
                add_user(
                    getattr(user, "username", ""),
                    getattr(user, "species", "human"),
                    getattr(user, "profile_pic", "") or getattr(user, "avatar_url", ""),
                    None,
                    True,
                )
    except Exception:
        pass

    try:
        if Proposal is not None:
            proposal_query = db.query(Proposal)
            if search_filter:
                proposal_query = proposal_query.filter(Proposal.userName.ilike(search_filter))
            rows = proposal_query.order_by(desc(Proposal.id)).limit(240).all()
            for row in rows:
                add_user(
                    getattr(row, "userName", None) or getattr(row, "author", "") or "Unknown",
                    getattr(row, "author_type", "human"),
                    getattr(row, "author_img", ""),
                    getattr(row, "id", 0),
                    False,
                )
    except Exception:
        try:
            params: Dict[str, Any] = {}
            query_text = "SELECT id, userName, author_type, author_img FROM proposals"
            if search_filter:
                query_text += " WHERE LOWER(userName) LIKE LOWER(:search)"
                params["search"] = search_filter
            query_text += " ORDER BY id DESC LIMIT 240"
            rows = db.execute(text(query_text), params).fetchall()
            for row in rows:
                mapping = getattr(row, "_mapping", {})
                add_user(
                    getattr(row, "userName", None) or mapping.get("userName", ""),
                    getattr(row, "author_type", None) or mapping.get("author_type", "human"),
                    getattr(row, "author_img", None) or mapping.get("author_img", ""),
                    getattr(row, "id", None) or mapping.get("id", 0),
                    False,
                )
        except Exception:
            pass

    return sorted(
        users.values(),
        key=lambda item: (int(item.get("latest_post_id", 0)), int(item.get("post_count", 0))),
        reverse=True,
    )[:limit]


def _build_status_payload(db: Session) -> Dict:
    total_harmonizers = 0
    total_vibenodes = 0
    total_proposals = 0
    total_comments = 0
    total_votes = 0

    try:
        if CRUD_MODELS_AVAILABLE:
            total_harmonizers = db.query(Harmonizer).count()
            total_vibenodes = db.query(VibeNode).count() if VibeNode is not None else 0
            total_proposals = db.query(Proposal).count()
            total_comments = db.query(Comment).count()
            total_votes = db.query(ProposalVote).count()
        else:
            total_harmonizers = db.execute(text("SELECT COUNT(*) FROM harmonizers")).scalar() or 0
            total_vibenodes = db.execute(text("SELECT COUNT(*) FROM vibenodes")).scalar() or 0
            total_proposals = db.execute(text("SELECT COUNT(*) FROM proposals")).scalar() or 0
            total_comments = db.execute(text("SELECT COUNT(*) FROM comments")).scalar() or 0
            total_votes = db.execute(text("SELECT COUNT(*) FROM proposal_votes")).scalar() or 0
    except Exception:
        pass

    return {
        "status": "online",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "metrics": {
            "total_harmonizers": int(total_harmonizers or 0),
            "total_vibenodes": int(total_vibenodes or total_proposals or 0),
            "community_wellspring": str((total_votes or 0) + (total_comments or 0)),
            "current_system_entropy": round(max(1.0, (total_proposals or 0) * 0.4 + (total_comments or 0) * 0.2), 2),
        },
        "mission": "To create order and meaning from chaos through collective resonance.",
    }


def _build_network_payload(db: Session, limit: int = 100) -> Dict:
    nodes: List[Dict] = []
    edges: List[Dict] = []
    seen_users: Dict[str, Dict] = {}

    proposals = []
    if CRUD_MODELS_AVAILABLE:
        proposals = (
            db.query(Proposal)
            .order_by(desc(Proposal.id))
            .limit(limit)
            .all()
        )
    else:
        proposals = db.execute(
            text(
                "SELECT id, title, userName, author_type, created_at "
                "FROM proposals ORDER BY id DESC LIMIT :limit"
            ),
            {"limit": limit},
        ).fetchall()

    for proposal in proposals:
        proposal_id = getattr(proposal, "id", None)
        username = getattr(proposal, "userName", None) or getattr(proposal, "author_username", None) or f"user-{proposal_id}"
        author_type = getattr(proposal, "author_type", None) or "human"
        user_id = f"user:{username}"
        proposal_node_id = f"proposal:{proposal_id}"

        if user_id not in seen_users:
            user_node = {
                "id": user_id,
                "label": username,
                "type": "harmonizer",
            }
            seen_users[user_id] = user_node
            nodes.append(user_node)

        nodes.append(
            {
                "id": proposal_node_id,
                "label": getattr(proposal, "title", None) or f"Proposal {proposal_id}",
                "type": "proposal",
                "echo": 0,
            }
        )
        edges.append(
            {
                "source": user_id,
                "target": proposal_node_id,
                "type": f"authored_by_{author_type}",
                "strength": 1,
            }
        )

    node_count = len(nodes)
    edge_count = len(edges)
    density = 0.0
    if node_count > 1:
        density = round(edge_count / (node_count * (node_count - 1)), 4)

    return {
        "nodes": nodes,
        "edges": edges,
        "metrics": {
            "node_count": node_count,
            "edge_count": edge_count,
            "density": density,
        },
    }


def _collect_author_nodes(db: Session, author_type: str, limit: int = 5) -> List[Dict]:
    nodes: List[Dict] = []
    try:
        if CRUD_MODELS_AVAILABLE:
            count_expr = func.count(Proposal.id)
            rows = (
                db.query(Proposal.userName, count_expr.label("posts"))
                .filter(Proposal.author_type == author_type)
                .group_by(Proposal.userName)
                .order_by(desc(count_expr))
                .limit(limit)
                .all()
            )
            for name, posts in rows:
                clean_name = (name or "").strip()
                if clean_name:
                    nodes.append({"name": clean_name, "posts": int(posts or 0), "type": author_type})
        else:
            rows = db.execute(
                text(
                    """
                    SELECT userName, COUNT(*) AS posts
                    FROM proposals
                    WHERE author_type = :author_type
                    GROUP BY userName
                    ORDER BY posts DESC
                    LIMIT :limit
                    """
                ),
                {"author_type": author_type, "limit": limit},
            ).fetchall()
            for row in rows:
                clean_name = str(getattr(row, "userName", "") or row[0] or "").strip()
                if clean_name:
                    nodes.append({"name": clean_name, "posts": int(getattr(row, "posts", 0) or row[1] or 0), "type": author_type})
    except Exception:
        nodes = []
    return nodes


def _build_supernova_menu_payload(db: Session, username: Optional[str] = None) -> Dict:
    status_payload = _build_status_payload(db)
    network_payload = _build_network_payload(db, limit=60)

    orgs = _collect_author_nodes(db, "company", limit=4)
    agents = _collect_author_nodes(db, "ai", limit=4)

    if not orgs:
        orgs = [
            {"name": "superNova 2177 Inc.", "posts": 0, "type": "company"},
            {"name": "AccessAI protocol node", "posts": 0, "type": "company"},
        ]
    if not agents:
        agents = [
            {"name": "Weighted Vote Agent", "posts": 0, "type": "ai"},
            {"name": "Network Resonance Agent", "posts": 0, "type": "ai"},
            {"name": "Remix Governance Agent", "posts": 0, "type": "ai"},
        ]

    return {
        "profile": {
            "username": username or "SuperNova harmonizer",
            "status": "online",
            "species_model": "AI x Humans x ORG",
        },
        "status": status_payload,
        "network": network_payload.get("metrics", {}),
        "orgs": orgs,
        "agents": agents,
        "capabilities": [
            {"key": "weighted_voting", "label": "Tri-species weighted voting", "available": True},
            {"key": "karma_system", "label": "Harmony and karma signals", "available": SUPER_NOVA_AVAILABLE},
            {"key": "network_analysis", "label": "Network resonance map", "available": True},
            {"key": "governance", "label": "Governance decisions and runs", "available": SUPER_NOVA_AVAILABLE},
            {"key": "remix_protocol", "label": "Fork/remix protocol hooks", "available": SUPER_NOVA_AVAILABLE},
        ],
    }

# --- Universe Info Endpoint ---
@app.get("/universe/info", tags=["System"])
def universe_info():
    """Return details about the current database configuration."""
    if not SUPER_NOVA_AVAILABLE:
        # Fallback response when SuperNova is not available
        return {
            "mode": "standalone",
            "engine": "sqlite:///fallback.db", 
            "universe_id": "standalone_universe",
            "note": "SuperNova integration not available"
        }
    
    try:
        s = get_settings()
        return {
            "mode": s.DB_MODE,
            "engine": DB_ENGINE_URL or s.engine_url,
            "universe_id": s.UNIVERSE_ID,
        }
    except Exception as e:
        return {
            "error": f"Failed to get universe info: {str(e)}",
            "mode": "error",
            "engine": "unknown",
            "universe_id": "error"
        }

def _normalize_preview_domain(domain: str) -> str:
    candidate = (domain or "").strip().lower()
    if not candidate:
        raise HTTPException(status_code=400, detail="Domain is required")
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.netloc or parsed.path or "").split("/")[0].split(":")[0].strip(".")
    if (
        not host
        or host in {"localhost", "127.0.0.1", "::1"}
        or "." not in host
        or any(char.isspace() for char in host)
    ):
        raise HTTPException(status_code=400, detail="Use a public domain such as example.com")
    return host


def _normalize_preview_username(username: str) -> str:
    clean_username = (username or "").strip()
    if not clean_username or any(char.isspace() for char in clean_username):
        raise HTTPException(status_code=400, detail="Username is required")
    return clean_username[:80]


@app.get("/.well-known/supernova", summary="Describe this SuperNova instance")
@app.get("/.well-known/supernova.json", summary="Describe this SuperNova instance")
def supernova_well_known():
    host = urlparse(PUBLIC_BASE_URL).netloc or "2177.tech"
    payload = {
        "service": "SuperNova 2177",
        "schema": "supernova.instance_manifest.v1",
        "version": SUPERNOVA_INSTANCE_VERSION,
        "public_base_url": PUBLIC_BASE_URL,
        "open_federation": True,
        "cors": {
            "public_reads": "*" if CORS_CONFIG["public_api_cors_open"] else "allowlist",
            "credentials": False,
            "mode": CORS_CONFIG["mode"],
        },
        "endpoints": {
            "health": f"{PUBLIC_BASE_URL}/health",
            "status": f"{PUBLIC_BASE_URL}/supernova-status",
            "webfinger": f"{PUBLIC_BASE_URL}/.well-known/webfinger?resource=acct:{{username}}@{host}",
            "profile_json": f"{PUBLIC_BASE_URL}/profile/{{username}}",
            "actor": f"{PUBLIC_BASE_URL}/actors/{{username}}",
            "outbox": f"{PUBLIC_BASE_URL}/actors/{{username}}/outbox",
            "portable_profile": f"{PUBLIC_BASE_URL}/u/{{username}}/export.json",
            "domain_verification_preview": f"{PUBLIC_BASE_URL}/domain-verification/preview?domain={{domain}}&username={{username}}",
        },
        "identity": {
            "local_handle": "username",
            "canonical_domain_field": "claimed_domain",
            "verified_domain_field": "verified_domain",
            "did_method": "did:web",
            "domain_verified_requires_proof": True,
        },
        "domain_verification": {
            "status": "planned",
            "claimed_domains_are_not_verified": True,
            "planned_methods": ["https_well_known", "dns_txt"],
            "https_well_known_path": "/.well-known/supernova",
            "dns_txt_label": "_supernova",
        },
        "federation": {
            "mode": "read_only_discovery",
            "activitypub_inbox": False,
            "webmention_receiver": False,
            "remote_feed_mutation": False,
        },
        "governance": {
            "species": ["human", "ai", "company"],
            "three_species_protocol": True,
            "decision_flow": [
                "proposal",
                "ai_explanation_or_simulation",
                "three_species_vote",
                "decision_record",
                "execution_intent",
                "company_or_human_ratification",
                "manual_execution",
            ],
            "execution_current_mode": "manual_preview_only",
            "company_ratification_required": True,
            "automatic_execution": False,
            "ai_execution_without_ratification": False,
        },
        "organization_integration": {
            "status": "planned",
            "manifest_path": "/.well-known/supernova",
            "domain_verification_required": True,
            "current_mode": "read_only_manifest",
            "automatic_execution": False,
            "company_webhooks": False,
            "allowed_actions": [],
        },
        "protocol_schemas": {
            "organization_manifest": f"{PUBLIC_BASE_URL}/protocol/supernova.organization.schema.json",
            "execution_intent": f"{PUBLIC_BASE_URL}/protocol/supernova.execution-intent.schema.json",
            "three_species_vote": f"{PUBLIC_BASE_URL}/protocol/supernova.three-species-vote.schema.json",
            "portable_profile": f"{PUBLIC_BASE_URL}/protocol/supernova.portable-profile.schema.json",
            "examples": f"{PUBLIC_BASE_URL}/protocol/examples/",
        },
        "protocol_examples": {
            "organization_manifest": f"{PUBLIC_BASE_URL}/protocol/examples/example-organization-manifest.json",
            "execution_intent": f"{PUBLIC_BASE_URL}/protocol/examples/example-execution-intent.json",
            "three_species_vote": f"{PUBLIC_BASE_URL}/protocol/examples/example-three-species-vote.json",
            "portable_profile": f"{PUBLIC_BASE_URL}/protocol/examples/example-portable-profile.json",
        },
        "schema_version_policy": {
            "current_version": "v1",
            "v1_execution_posture": "manual_preview_only",
            "v1_automatic_execution": False,
            "v1_company_webhooks": False,
            "breaking_changes_require_new_schema_version": True,
        },
        "public_data_policy": {
            "public_exports_only": True,
            "excluded_fields": [
                "email",
                "password_hash",
                "access_token",
                "refresh_token",
                "direct_messages",
                "private_message_metadata",
                "secrets",
                "admin_state",
                "debug_state",
            ],
        },
    }
    return JSONResponse(payload, headers=PUBLIC_FEDERATION_CACHE_HEADERS)


@app.get("/domain-verification/preview", summary="Preview domain verification instructions")
def domain_verification_preview(domain: str = Query(...), username: str = Query(...)):
    host = _normalize_preview_domain(domain)
    clean_username = _normalize_preview_username(username)
    profile_url = f"{PUBLIC_BASE_URL}/users/{clean_username}"
    actor_url = f"{PUBLIC_BASE_URL}/actors/{clean_username}"
    well_known_url = f"https://{host}/.well-known/supernova"
    return JSONResponse(
        {
            "schema": "supernova.domain_verification_preview.v1",
            "status": "preview_only",
            "does_not_verify_yet": True,
            "domain": host,
            "username": clean_username,
            "methods": {
                "https_well_known": {
                    "url": well_known_url,
                    "expected_example": {
                        "schema": "supernova.organization_manifest.v1",
                        "manifest_type": "organization",
                        "organization": {
                            "name": clean_username,
                            "domain": host,
                            "canonical_actor": actor_url,
                            "supernova_profile": profile_url,
                        },
                        "governance": {
                            "three_species_protocol": True,
                            "species": ["human", "ai", "company"],
                            "equal_species_weight": True,
                            "company_ratification_required": True,
                            "human_supervision_required": True,
                        },
                        "execution": {
                            "current_mode": "manual_only",
                            "automatic_execution": False,
                            "webhooks_enabled": False,
                            "allowed_actions": [],
                        },
                        "value_sharing": {
                            "status": "not_financial_protocol",
                            "company_side_policy_required": True,
                            "supernova_nonprofit_does_not_custody_funds": True,
                        },
                    },
                },
                "dns_txt": {
                    "name": f"_supernova.{host}",
                    "value": f"supernova-profile={profile_url}",
                },
            },
            "safety": {
                "external_fetch": False,
                "dns_lookup": False,
                "database_write": False,
                "marks_domain_verified": False,
            },
        },
        headers=PUBLIC_FEDERATION_CACHE_HEADERS,
    )


app.include_router(create_status_router(
    get_db=get_db,
    db_engine_url=DB_ENGINE_URL,
    cors_config=CORS_CONFIG,
    runtime=_runtime,
    supernova_available=SUPER_NOVA_AVAILABLE,
    supernova_core_routes=SUPER_NOVA_CORE_ROUTES,
    status_payload_builder=_build_status_payload,
))

@app.get("/universe", summary="Get simplified universe state")
def get_universe_state():
    """
    Returns a mock representation of the current universe graph,
    including proposals, decisions, and links.
    """
    return {
        "nodes": [
            {"id": "u1", "label": "Proposal A", "type": "proposal", "votes": {"human": 12, "company": 5, "ai": 2}},
            {"id": "u2", "label": "Decision B", "type": "decision", "votes": {"human": 4, "company": 10, "ai": 1}},
        ],
        "links": [
            {"source": "u1", "target": "u2"},
        ]
    }
   
@app.get("/network-analysis/", tags=["System"])
def get_network_analysis(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    return _build_network_payload(db, limit=limit)


@app.get("/supernova-menu", tags=["System"])
def get_supernova_menu(username: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return _build_supernova_menu_payload(db, username=username)


@app.post("/users/register", tags=["Harmonizers"])
def register_user(payload: RegisterUserIn, db: Session = Depends(get_db)):
    if Harmonizer is None:
        raise HTTPException(status_code=503, detail="User system unavailable")

    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    species = _normalize_public_account_species(payload.species)
    existing = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == username.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    email = (payload.email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="A valid email is required")
    email_owner = db.query(Harmonizer).filter(func.lower(Harmonizer.email) == email).first()
    if email_owner:
        raise HTTPException(status_code=409, detail="Email already exists")

    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")

    hashed_password = _hash_password_strict(payload.password)

    user = Harmonizer(
        username=username,
        email=email,
        hashed_password=hashed_password,
        species=species,
        bio=payload.bio or "",
        profile_pic="default.jpg",
        is_active=True,
        consent_given=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "species": user.species,
        "harmony_score": str(getattr(user, "harmony_score", "100.0")),
        "creative_spark": str(getattr(user, "creative_spark", "1000000.0")),
        "network_centrality": float(getattr(user, "network_centrality", 0.0)),
        "bio": getattr(user, "bio", ""),
    }


@app.post("/auth/login", tags=["Auth"])
def credential_login(payload: CredentialLoginIn, db: Session = Depends(get_db)):
    if Harmonizer is None:
        raise HTTPException(status_code=503, detail="User system unavailable")

    username = payload.username.strip()
    password = payload.password
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == username.lower()).first()
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    hashed_password = getattr(user, "hashed_password", "") or ""
    verified, legacy_sha = _verify_password_with_legacy_upgrade(password, hashed_password)

    if not verified:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=400, detail="Inactive user")

    if legacy_sha:
        try:
            user.hashed_password = _hash_password_strict(password)
            db.add(user)
            db.commit()
            db.refresh(user)
        except HTTPException:
            db.rollback()

    token = _create_wrapper_access_token(user.username) or uuid.uuid4().hex

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _public_user_payload(user, provider="password"),
    }


@app.get("/auth/social/profile", tags=["Auth"])
def get_social_auth_profile(
    provider: Optional[str] = Query("oauth"),
    provider_id: Optional[str] = Query(""),
    email: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    user = _find_social_user(db, provider or "oauth", provider_id or "", email or "")
    if not user:
        return {"exists": False}
    return {
        "exists": True,
        **_public_user_payload(user, provider=(provider or "oauth").strip().lower()),
    }


@app.post("/auth/social/sync", tags=["Auth"])
def sync_social_auth(payload: SocialAuthSyncIn, db: Session = Depends(get_db)):
    provider = (payload.provider or "oauth").strip().lower()
    provider_id = (payload.provider_id or "").strip()
    email = (payload.email or "").strip().lower()
    username = (
        (payload.username or "").strip()
        or (email.split("@", 1)[0] if email else "")
        or f"{provider}-{provider_id[:8] or uuid.uuid4().hex[:8]}"
    )
    avatar_url = (payload.avatar_url or "").strip()
    species = None
    if payload.species:
        raw_species = str(payload.species).strip()
        if raw_species.lower() == "ai":
            raise HTTPException(status_code=400, detail=PUBLIC_ACCOUNT_AI_SPECIES_ERROR)
        try:
            species = _normalize_public_account_species(payload.species)
        except HTTPException:
            species = None

    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not email:
        email = f"{provider_id or uuid.uuid4().hex}@{provider}.oauth.supernova"

    if Harmonizer is None:
        return {
            "id": None,
            "username": username,
            "email": email,
            "provider": provider,
            "species": species or "human",
            "avatar_url": _social_avatar(avatar_url),
            "backend": "fallback",
        }

    existing = _find_social_user(db, provider, provider_id, email)
    if not existing:
        existing = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == username.lower()).first()

    if existing:
        avatar_to_sync = ""
        existing_avatar = getattr(existing, "profile_pic", "") or getattr(existing, "avatar_url", "") or ""
        should_update_avatar = bool(avatar_url) and (
            _is_default_avatar(existing_avatar)
            or (_is_uploaded_avatar(avatar_url) and not _is_uploaded_avatar(existing_avatar))
        )
        if should_update_avatar:
            existing.profile_pic = avatar_url
            avatar_to_sync = avatar_url
        if not getattr(existing, "species", None):
            existing.species = species or "human"
        existing.is_active = True
        existing.consent_given = True
        db.add(existing)
        db.commit()
        db.refresh(existing)
        if avatar_to_sync:
            _sync_user_avatar_references(db, existing.username, avatar_to_sync, getattr(existing, "id", None))
        return {
            "id": existing.id,
            "username": existing.username,
            "email": existing.email,
            "provider": provider,
            "species": existing.species,
            "avatar_url": _social_avatar(getattr(existing, "profile_pic", "") or avatar_url),
            "backend": "supernovacore",
            **_auth_fields_for_user(existing),
        }

    candidate = username
    suffix = 2
    while db.query(Harmonizer).filter(func.lower(Harmonizer.username) == candidate.lower()).first():
        candidate = f"{username}-{suffix}"
        suffix += 1

    raw_secret = f"{provider}:{provider_id or email}:{candidate}"
    hashed_password = _hash_password_strict(raw_secret)

    user = Harmonizer(
        username=candidate,
        email=email,
        hashed_password=hashed_password,
        species=species or "human",
        bio=f"Signed in with {provider}.",
        profile_pic=avatar_url or "default.jpg",
        is_active=True,
        consent_given=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "provider": provider,
        "species": user.species,
        "avatar_url": _social_avatar(getattr(user, "profile_pic", "")),
        "backend": "supernovacore",
        **_auth_fields_for_user(user),
    }

#
@app.get("/debug-supernova")
def debug_supernova():
    if _is_explicit_production_environment():
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "supernova_available": SUPER_NOVA_AVAILABLE,
        "supernova": build_supernova_runtime_payload(_runtime, SUPER_NOVA_AVAILABLE, include_routes=True),
        "debug_mode": "development",
    }

@app.get("/debug/search-test")
def debug_search(search: str = Query(...), db: Session = Depends(get_db)):
    if _is_explicit_production_environment():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        if CRUD_MODELS_AVAILABLE:
            results = db.query(Proposal).filter(
                or_(
                    Proposal.title.ilike(f"%{search}%"),
                    Proposal.description.ilike(f"%{search}%"),
                    Proposal.userName.ilike(f"%{search}%")
                )
            ).limit(5).all()
            
            return {
                "search_term": search,
                "found_proposals": len(results),
                "results": [
                    {"id": r.id, "title": r.title, "author": r.userName} 
                    for r in results
                ],
                "method": "orm"
            }
        else:
            result = db.execute(
                text(
                    "SELECT id, title, userName FROM proposals "
                    "WHERE title ILIKE :search OR description ILIKE :search OR userName ILIKE :search "
                    "LIMIT 5"
                ),
                {"search": f"%{search}%"}
            )
            rows = result.fetchall()
            
            return {
                "search_term": search,
                "found_proposals": len(rows),
                "results": [dict(row) for row in rows],
                "method": "sql"
            }
    except Exception as e:
        return {"error": str(e), "query_working": False}

#
@app.get("/profile/{username}", summary="Get user profile")
def profile(username: str, db: Session = Depends(get_db)):
    try:
        if Harmonizer is not None:
            user = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == username.lower()).first()
            if user:
                avatar_value = getattr(user, "profile_pic", "") or getattr(user, "avatar_url", "") or ""
                follow_counts = _follow_counts(user.username)
                metadata = _profile_metadata(db, user.username)
                return {
                    "username": user.username,
                    "avatar_url": _social_avatar(avatar_value),
                    "bio": user.bio or "",
                    "domain_url": metadata.get("domain_url", ""),
                    "domain_as_profile": bool(metadata.get("domain_as_profile", False)),
                    "followers": follow_counts["followers"],
                    "following": follow_counts["following"],
                    "status": "online",
                    "karma": float(getattr(user, 'karma_score', 0)),
                    "harmony_score": float(getattr(user, 'harmony_score', 0)),
                    "creative_spark": float(getattr(user, 'creative_spark', 0)),
                    "species": getattr(user, 'species', 'human')
                }
    except Exception as e:
        print(f"Error fetching SuperNova profile: {e}")

    try:
        if Proposal is not None:
            latest = (
                db.query(Proposal)
                .filter(func.lower(Proposal.userName) == username.lower())
                .order_by(desc(Proposal.id))
                .first()
            )
            post_count = db.query(Proposal).filter(func.lower(Proposal.userName) == username.lower()).count()
            if latest:
                follow_counts = _follow_counts(username)
                metadata = _profile_metadata(db, username)
                signal_harmony = min(
                    100.0,
                    float(post_count or 0) * 6.0
                    + float(follow_counts.get("followers", 0) or 0) * 1.2
                    + float(follow_counts.get("following", 0) or 0) * 0.25,
                )
                return {
                    "username": username,
                    "avatar_url": _social_avatar(getattr(latest, "author_img", "")),
                    "bio": "",
                    "domain_url": metadata.get("domain_url", ""),
                    "domain_as_profile": bool(metadata.get("domain_as_profile", False)),
                    "followers": follow_counts["followers"],
                    "following": follow_counts["following"],
                    "status": "online",
                    "karma": float(post_count or 0),
                    "harmony_score": signal_harmony,
                    "creative_spark": float(post_count or 0) * 10.0,
                    "species": getattr(latest, "author_type", "human"),
                    "post_count": post_count,
                }
    except Exception as e:
        print(f"Error fetching fallback profile from proposals: {e}")

    # Fallback
    return {
        "username": username,
        "avatar_url": "",
        "bio": "",
        "domain_url": "",
        "domain_as_profile": False,
        "followers": 2315,
        "following": 1523,
        "status": "online"
    }


def _public_profile_url(username: str) -> str:
    return f"{PUBLIC_BASE_URL}/users/{username}"


def _public_actor_url(username: str) -> str:
    return f"{PUBLIC_BASE_URL}/actors/{username}"


def _username_from_webfinger_resource(resource: str) -> str:
    raw = unquote((resource or "").strip())
    if raw.startswith("acct:"):
        handle = raw[5:]
        return handle.split("@", 1)[0].strip()
    parsed = urlparse(raw)
    parts = [part for part in parsed.path.split("/") if part]
    for marker in ("users", "u", "actors"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts):
                return parts[idx + 1].strip()
    return raw.strip()


def _profile_exists(db: Session, username: str) -> bool:
    clean_username = (username or "").strip()
    if not clean_username:
        return False
    try:
        if Harmonizer is not None:
            user = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == clean_username.lower()).first()
            if user:
                return True
        if Proposal is not None:
            return bool(
                db.query(Proposal)
                .filter(func.lower(Proposal.userName) == clean_username.lower())
                .first()
            )
    except Exception:
        return False
    return False


def _domain_did(domain_url: str) -> str:
    parsed = urlparse(domain_url or "")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return ""
    return f"did:web:{host}"


def _profile_identity_payload(db: Session, username: str) -> Dict[str, Any]:
    profile_payload = profile(username, db)
    clean_username = (profile_payload.get("username") or username or "").strip()
    claimed_domain_url = (profile_payload.get("domain_url") or "").strip()
    domain_as_profile = bool(profile_payload.get("domain_as_profile", False))
    local_profile_url = _public_profile_url(clean_username)
    canonical_url = claimed_domain_url if claimed_domain_url and domain_as_profile else local_profile_url
    verification_template = {}
    if claimed_domain_url:
        verification_template = {
            "supernova_profile": local_profile_url,
            "owner": clean_username,
            "claimed_domain": claimed_domain_url,
        }
    return {
        "username": clean_username,
        "display_name": clean_username,
        "species": profile_payload.get("species", "human"),
        "bio": profile_payload.get("bio", ""),
        "avatar_url": profile_payload.get("avatar_url", ""),
        "local_profile_url": local_profile_url,
        "canonical_url": canonical_url,
        "canonical_url_source": "claimed_domain" if claimed_domain_url and domain_as_profile else "supernova",
        "canonical_url_verified": False,
        "domain_url": claimed_domain_url,
        "claimed_domain": claimed_domain_url,
        "claimed_domain_url": claimed_domain_url,
        "domain_as_profile": domain_as_profile,
        "domain_verified": False,
        "verified_domain": "",
        "verified_domain_url": "",
        "verified_at": None,
        "verification_method": None,
        "did": _domain_did(claimed_domain_url),
        "actor_url": _public_actor_url(clean_username),
        "portable_export_url": f"{PUBLIC_BASE_URL}/u/{clean_username}/export.json",
        "verification_file": "/.well-known/supernova.json",
        "verification_template": verification_template,
    }


def _connector_public_web_url(path: str) -> str:
    return f"{PUBLIC_BASE_URL}{path}"


def _connector_author_context(db: Session, proposal) -> Dict[str, Any]:
    user_name = ""
    author_obj = None
    if CRUD_MODELS_AVAILABLE and getattr(proposal, "author_id", None):
        author_obj = db.query(Harmonizer).filter(Harmonizer.id == proposal.author_id).first()
        if author_obj and getattr(author_obj, "username", None):
            user_name = author_obj.username

    if not user_name:
        user_name = (
            getattr(proposal, "userName", None)
            or getattr(proposal, "author_username", None)
            or getattr(proposal, "author", None)
            or "Unknown"
        )
    if author_obj is None:
        author_obj = _find_harmonizer_by_username(db, user_name)

    avatar_value = getattr(proposal, "author_img", "")
    if author_obj is not None:
        avatar_value = getattr(author_obj, "profile_pic", None) or avatar_value

    return {
        "username": str(user_name),
        "species": getattr(author_obj, "species", None)
        or getattr(proposal, "author_type", "human")
        or "human",
        "avatar_url": _social_avatar(avatar_value),
        "profile_url": _connector_public_web_url(f"/users/{user_name}"),
    }


def _connector_vote_summary(db: Session, proposal_id: int) -> Dict[str, Any]:
    return _public_vote_summary(db, proposal_id)


def _connector_proposal_payload(db: Session, proposal, include_text: bool = True) -> Dict[str, Any]:
    proposal_id = getattr(proposal, "id", None)
    author = _connector_author_context(db, proposal)
    payload = {
        "id": proposal_id,
        "type": "proposal",
        "title": getattr(proposal, "title", "") or "",
        "author": author,
        "created_at": _format_timestamp(
            getattr(proposal, "created_at", None) or getattr(proposal, "date", None)
        ),
        "web_url": _connector_public_web_url(f"/proposals/{proposal_id}"),
        "vote_summary": _connector_vote_summary(db, proposal_id),
        "collabs": _approved_proposal_collabs(db, proposal_id),
        "media": _media_payload(
            getattr(proposal, "image", ""),
            getattr(proposal, "video", ""),
            getattr(proposal, "link", ""),
            getattr(proposal, "file", ""),
            getattr(proposal, "payload", None),
            getattr(proposal, "voting_deadline", None),
        ),
    }
    if include_text:
        payload["text"] = (
            getattr(proposal, "description", None)
            or getattr(proposal, "body", None)
            or ""
        )
    return payload


def _connector_get_proposal_or_404(db: Session, proposal_id: int):
    if CRUD_MODELS_AVAILABLE:
        proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
    else:
        proposal = db.execute(
            text("SELECT * FROM proposals WHERE id = :proposal_id"),
            {"proposal_id": proposal_id},
        ).fetchone()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


def _connector_profile_payload(db: Session, username: str) -> Dict[str, Any]:
    clean_username = (username or "").strip()
    if not clean_username:
        raise HTTPException(status_code=404, detail="Profile not found")

    user = None
    latest_post = None
    post_count = 0
    if CRUD_MODELS_AVAILABLE:
        user = (
            db.query(Harmonizer)
            .filter(func.lower(Harmonizer.username) == clean_username.lower())
            .first()
        )
        latest_post = (
            db.query(Proposal)
            .filter(func.lower(Proposal.userName) == clean_username.lower())
            .order_by(desc(Proposal.id))
            .first()
        )
        post_count = (
            db.query(Proposal)
            .filter(func.lower(Proposal.userName) == clean_username.lower())
            .count()
        )
    else:
        latest_post = db.execute(
            text(
                "SELECT * FROM proposals WHERE lower(userName) = lower(:username) "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"username": clean_username},
        ).fetchone()
        post_count = int(
            db.execute(
                text("SELECT COUNT(*) FROM proposals WHERE lower(userName) = lower(:username)"),
                {"username": clean_username},
            ).scalar()
            or 0
        )

    if user is None and latest_post is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    resolved_username = getattr(user, "username", None) or clean_username
    avatar_value = getattr(user, "profile_pic", None) or getattr(latest_post, "author_img", "") or ""
    species = getattr(user, "species", None) or getattr(latest_post, "author_type", None) or "human"
    follow_counts = _follow_counts(resolved_username)

    return {
        "username": resolved_username,
        "type": "profile",
        "species": species,
        "bio": getattr(user, "bio", "") if user is not None else "",
        "avatar_url": _social_avatar(avatar_value),
        "web_url": _connector_public_web_url(f"/users/{resolved_username}"),
        "post_count": post_count,
        "followers": follow_counts["followers"],
        "following": follow_counts["following"],
    }


@app.get("/connector/supernova", summary="Describe the public read-only SuperNova connector facade")
def connector_supernova_discovery():
    return {
        "name": "SuperNova",
        "mode": "public_read_only",
        "description": "Prototype SuperNova-owned public read facade for future connector surfaces.",
        "resources": ["profiles", "proposals", "comments", "vote_summaries", "ai_actor_profiles", "system_ai_reviews", "public_protocol_docs"],
        "endpoints": {
            "proposals": "/connector/proposals?search=&limit=&offset=",
            "proposal": "/connector/proposals/{id}",
            "proposal_comments": "/connector/proposals/{id}/comments?limit=&offset=",
            "proposal_votes": "/connector/proposals/{id}/votes",
            "system_ai_review": "/proposals/{id}/system-ai-review",
            "ai_review_ledger": "/proposals/{id}/ai-review-ledger",
            "ai_actor": "/ai-actors/{username}",
            "profile": "/connector/profiles/{username}",
            "spec": "/connector/supernova/spec",
        },
        "write_tools_enabled": False,
        "private_user_state_exposed": False,
        "action_tools": [],
        "safety": {
            "read_only": True,
            "public_only": True,
            "requires_auth": False,
            "no_private_notifications": True,
            "no_pending_collab_requests": True,
            "no_protected_core_internals": True,
        },
    }


@app.get("/connector/supernova/spec", summary="Describe the public read-only connector metadata shape")
def connector_supernova_spec():
    return {
        "name": "SuperNova",
        "mode": "public_read_only",
        "base_url": PUBLIC_BASE_URL,
        "resources": {
            "profiles": {
                "endpoint": "/connector/profiles/{username}",
                "summary": "Public profile identity, species, bio, avatar, public web URL, and public counts.",
                "parameters": {
                    "username": {"in": "path", "type": "string", "required": True},
                },
                "response_shape": {
                    "mode": "public_read_only",
                    "resource": "profile",
                    "item": ["username", "type", "species", "bio", "avatar_url", "web_url", "post_count"],
                },
            },
            "proposals": {
                "endpoint": "/connector/proposals",
                "summary": "Public proposal/post search and list results.",
                "parameters": {
                    "search": {"in": "query", "type": "string", "required": False},
                    "limit": {"in": "query", "type": "integer", "required": False, "default": 20, "maximum": 50},
                    "offset": {"in": "query", "type": "integer", "required": False, "default": 0},
                },
                "response_shape": {
                    "mode": "public_read_only",
                    "resource": "proposals",
                    "items": ["id", "type", "title", "text", "author", "created_at", "web_url", "vote_summary", "collabs", "media"],
                },
            },
            "proposal": {
                "endpoint": "/connector/proposals/{id}",
                "summary": "One public proposal/post by id.",
                "parameters": {
                    "id": {"in": "path", "type": "integer", "required": True},
                },
                "response_shape": {
                    "mode": "public_read_only",
                    "resource": "proposal",
                    "item": ["id", "type", "title", "text", "author", "created_at", "web_url", "vote_summary", "collabs", "media"],
                },
            },
            "comments": {
                "endpoint": "/connector/proposals/{id}/comments",
                "summary": "Public comments for one proposal/post.",
                "parameters": {
                    "id": {"in": "path", "type": "integer", "required": True},
                    "limit": {"in": "query", "type": "integer", "required": False, "default": 20, "maximum": 100},
                    "offset": {"in": "query", "type": "integer", "required": False, "default": 0},
                },
                "response_shape": {
                    "mode": "public_read_only",
                    "resource": "comments",
                    "items": ["id", "proposal_id", "parent_comment_id", "user", "species", "comment", "created_at"],
                },
            },
            "vote_summaries": {
                "endpoint": "/connector/proposals/{id}/votes",
                "embedded_in": ["proposals", "proposal"],
                "summary": "Public aggregate support/opposition counts exposed as vote_summary.",
                "parameters": {
                    "id": {"in": "path", "type": "integer", "required": True},
                },
                "response_shape": ["up", "down", "support", "oppose", "total", "approval_ratio"],
            },
        },
        "endpoints": {
            "discovery": "/connector/supernova",
            "spec": "/connector/supernova/spec",
            "proposals": "/connector/proposals",
            "proposal": "/connector/proposals/{id}",
            "proposal_comments": "/connector/proposals/{id}/comments",
            "proposal_votes": "/connector/proposals/{id}/votes",
            "profile": "/connector/profiles/{username}",
        },
        "parameters": {
            "search": {"type": "string", "used_by": ["/connector/proposals"]},
            "limit": {"type": "integer", "used_by": ["/connector/proposals", "/connector/proposals/{id}/comments"]},
            "offset": {"type": "integer", "used_by": ["/connector/proposals", "/connector/proposals/{id}/comments"]},
        },
        "write_tools_enabled": False,
        "action_tools": [],
        "private_user_state_exposed": False,
        "safety": {
            "public_only": True,
            "read_only": True,
            "requires_auth": False,
            "no_private_notifications": True,
            "no_pending_collab_requests": True,
            "no_protected_core_internals": True,
            "no_writes": True,
        },
    }


@app.get("/connector/proposals", summary="Search public proposals through the read-only connector facade")
def connector_list_proposals(
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if CRUD_MODELS_AVAILABLE:
        query = db.query(Proposal)
        if search and search.strip():
            search_filter = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Proposal.title.ilike(search_filter),
                    Proposal.description.ilike(search_filter),
                    Proposal.userName.ilike(search_filter),
                )
            )
        proposals = query.order_by(desc(Proposal.created_at), desc(Proposal.id)).offset(offset).limit(limit).all()
    else:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        where_clause = ""
        if search and search.strip():
            where_clause = (
                "WHERE lower(title) LIKE lower(:search) "
                "OR lower(description) LIKE lower(:search) "
                "OR lower(userName) LIKE lower(:search)"
            )
            params["search"] = f"%{search.strip()}%"
        proposals = db.execute(
            text(
                f"SELECT * FROM proposals {where_clause} "
                "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        ).fetchall()

    return {
        "mode": "public_read_only",
        "resource": "proposals",
        "limit": limit,
        "offset": offset,
        "items": [_connector_proposal_payload(db, proposal, include_text=True) for proposal in proposals],
    }


@app.get("/connector/proposals/{proposal_id}", summary="Read one public proposal through the connector facade")
def connector_get_proposal(proposal_id: int, db: Session = Depends(get_db)):
    proposal = _connector_get_proposal_or_404(db, proposal_id)
    return {
        "mode": "public_read_only",
        "resource": "proposal",
        "item": _connector_proposal_payload(db, proposal, include_text=True),
    }


@app.get("/connector/proposals/{proposal_id}/votes", summary="Read public proposal vote summary through the connector facade")
def connector_get_proposal_vote_summary(proposal_id: int, db: Session = Depends(get_db)):
    _connector_get_proposal_or_404(db, proposal_id)
    return {
        "mode": "public_read_only",
        "resource": "proposal_vote_summary",
        "proposal_id": proposal_id,
        "vote_summary": _connector_vote_summary(db, proposal_id),
    }


app.include_router(create_ai_delegates_router(
    get_db=get_db,
    persona_draft_model=AiPersonaDraftIn,
    delegate_create_model=AiDelegateCreateIn,
    delegate_update_model=AiDelegateUpdateIn,
    get_current_harmonizer=lambda *args, **kwargs: get_current_harmonizer(*args, **kwargs),
    actor_custodian_type=_actor_custodian_type,
    ensure_ai_actors_table=_ensure_ai_actors_table,
    row_to_ai_actor_payload=_row_to_ai_actor_payload,
    normalize_ai_call_sign=_normalize_ai_call_sign,
    normalize_persona_traits=_normalize_persona_traits,
    generate_ai_delegate_username=_generate_ai_delegate_username,
    generate_ai_persona_draft=_generate_ai_persona_draft,
    ai_persona_traits=AI_PERSONA_TRAITS,
    get_ai_actor_row_by_username=_get_ai_actor_row_by_username,
    get_ai_actor_row_by_id=_get_ai_actor_row_by_id,
    create_delegate_harmonizer=_create_delegate_harmonizer,
    fallback_persona_draft=_fallback_persona_draft,
    coerce_persona_draft=_coerce_persona_draft,
    ai_persona_hash=_ai_persona_hash,
    json_dumps_compact=_json_dumps_compact,
    public_ai_actor_payload=_public_ai_actor_payload,
    normalize_disable_reason=_normalize_disable_reason,
    harmonizer_model=Harmonizer,
    system_ai_username=SUPERNOVA_SYSTEM_AI_USERNAME,
    system_ai_actor_payload=_system_ai_actor_payload,
    find_harmonizer_by_username=_find_harmonizer_by_username,
    ai_delegate_actor_metadata=_ai_delegate_actor_metadata,
    social_avatar=_social_avatar,
    supernova_ai_model_identity=SUPERNOVA_AI_MODEL_IDENTITY,
    supernova_ai_constitution_hash=SUPERNOVA_AI_CONSTITUTION_HASH,
    supernova_ai_prompt_policy_version=SUPERNOVA_AI_PROMPT_POLICY_VERSION,
    ai_persona_version=AI_PERSONA_VERSION,
    ai_persona_legal_status=AI_PERSONA_LEGAL_STATUS,
    ai_persona_custody_status=AI_PERSONA_CUSTODY_STATUS,
    ai_persona_future_independence_policy=AI_PERSONA_FUTURE_INDEPENDENCE_POLICY,
    ai_persona_independence_migration_status=AI_PERSONA_INDEPENDENCE_MIGRATION_STATUS,
))


app.include_router(create_ai_readonly_router(
    get_db=get_db,
    connector_get_proposal_or_404=_connector_get_proposal_or_404,
    system_ai_actor_payload=_system_ai_actor_payload,
    generate_locked_ai_review=_generate_locked_ai_review,
    connector_action_proposal_model=ConnectorActionProposal,
    connector_action_payload=lambda *args, **kwargs: _connector_action_payload(*args, **kwargs),
    proposal_vote_model=ProposalVote,
    harmonizer_model=Harmonizer,
    social_avatar=_social_avatar,
    format_timestamp=_format_timestamp,
    public_ai_actor_payload=_public_ai_actor_payload,
    connector_proposal_title=lambda *args, **kwargs: _connector_proposal_title(*args, **kwargs),
))


@app.get("/connector/proposals/{proposal_id}/comments", summary="Read public proposal comments through the connector facade")
def connector_get_proposal_comments(
    proposal_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _connector_get_proposal_or_404(db, proposal_id)
    if CRUD_MODELS_AVAILABLE:
        comments = (
            db.query(Comment)
            .filter(Comment.proposal_id == proposal_id)
            .order_by(Comment.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    else:
        comments = db.execute(
            text(
                "SELECT * FROM comments WHERE proposal_id = :proposal_id "
                "ORDER BY id ASC LIMIT :limit OFFSET :offset"
            ),
            {"proposal_id": proposal_id, "limit": limit, "offset": offset},
        ).fetchall()

    return {
        "mode": "public_read_only",
        "resource": "comments",
        "proposal_id": proposal_id,
        "limit": limit,
        "offset": offset,
        "items": [_serialize_comment_record(db, comment) for comment in comments],
    }


@app.get("/connector/profiles/{username}", summary="Read one public profile through the connector facade")
def connector_get_profile(username: str, db: Session = Depends(get_db)):
    return {
        "mode": "public_read_only",
        "resource": "profile",
        "item": _connector_profile_payload(db, username),
    }


def _connector_require_actor(
    authorization: Optional[str],
    db: Session,
    username: str,
):
    clean_username = (username or "").strip()
    if not clean_username:
        raise HTTPException(status_code=400, detail="username is required")
    return _require_token_identity_match(authorization, db, clean_username)


def _connector_require_ai_actor(
    authorization: Optional[str],
    db: Session,
    username: str,
):
    actor = _connector_require_actor(authorization, db, username)
    species = (getattr(actor, "species", "") or "").strip().lower()
    if species != "ai":
        raise HTTPException(status_code=403, detail="AI review drafts require an AI actor")
    return actor


def _connector_proposal_title(proposal) -> str:
    return getattr(proposal, "title", "") or "Untitled proposal"


def _connector_proposal_owner_username(db: Session, proposal) -> str:
    owner = (
        getattr(proposal, "userName", None)
        or getattr(proposal, "author", None)
        or ""
    )
    if owner:
        return str(owner)
    author_id = getattr(proposal, "author_id", None)
    if author_id and Harmonizer is not None:
        author = db.query(Harmonizer).filter(Harmonizer.id == author_id).first()
        return getattr(author, "username", "") if author else ""
    return ""


def _normalize_connector_vote_choice(choice: str) -> Dict[str, str]:
    clean_choice = (choice or "").strip().lower()
    mapping = {
        "support": ("support", "up"),
        "up": ("support", "up"),
        "oppose": ("oppose", "down"),
        "down": ("oppose", "down"),
        "abstain": ("abstain", "neutral"),
        "neutral": ("abstain", "neutral"),
    }
    if clean_choice not in mapping:
        raise HTTPException(status_code=400, detail="Invalid vote choice")
    intended_choice, normalized_vote = mapping[clean_choice]
    return {
        "intended_choice": intended_choice,
        "normalized_vote": normalized_vote,
    }


def _create_connector_action_draft(
    db: Session,
    *,
    action_type: str,
    actor_user_id: int,
    target_type: str,
    target_id: Optional[Any],
    draft_payload: Dict[str, Any],
):
    if ConnectorActionProposal is None:
        raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")
    record = ConnectorActionProposal(
        action_type=action_type,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        draft_payload=draft_payload,
        status="draft",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _connector_draft_response(record, summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "mode": "draft_only",
        "executed": False,
        "action_proposal": {
            "id": getattr(record, "id", None),
            "status": getattr(record, "status", "draft"),
            "action_type": getattr(record, "action_type", ""),
            "actor_user_id": getattr(record, "actor_user_id", None),
            "target_type": getattr(record, "target_type", ""),
            "target_id": getattr(record, "target_id", None),
        },
        "summary": summary,
        "safety": {
            "requires_approval": True,
            "no_execution": True,
            "no_write_action_performed": True,
        },
    }


def _connector_action_payload(value) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _connector_action_response(record, summary: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    executed_action = result.get("executed_action") or "vote"
    return {
        "ok": True,
        "mode": "approval_required",
        "executed": True,
        "action_proposal": {
            "id": getattr(record, "id", None),
            "status": getattr(record, "status", ""),
            "action_type": getattr(record, "action_type", ""),
            "actor_user_id": getattr(record, "actor_user_id", None),
            "target_type": getattr(record, "target_type", ""),
            "target_id": getattr(record, "target_id", None),
        },
        "summary": summary,
        "result": result,
        "safety": {
            "explicit_approval": True,
            "no_background_execution": True,
            "executed_action": executed_action,
        },
    }


CONNECTOR_ACTION_STATUSES = {"draft", "approved", "executed", "canceled", "failed"}


def _serialize_connector_action(record) -> Dict[str, Any]:
    return {
        "id": getattr(record, "id", None),
        "action_type": getattr(record, "action_type", ""),
        "actor_user_id": getattr(record, "actor_user_id", None),
        "target_type": getattr(record, "target_type", ""),
        "target_id": getattr(record, "target_id", None),
        "status": getattr(record, "status", ""),
        "draft_payload": _connector_action_payload(getattr(record, "draft_payload", None)),
        "result_payload": _connector_action_payload(getattr(record, "result_payload", None)),
        "created_at": _format_timestamp(getattr(record, "created_at", None)),
        "approved_at": _format_timestamp(getattr(record, "approved_at", None)),
        "executed_at": _format_timestamp(getattr(record, "executed_at", None)),
    }


def _connector_execute_vote(db: Session, *, actor, proposal, choice: str) -> Dict[str, Any]:
    if ProposalVote is None or Harmonizer is None:
        raise HTTPException(status_code=503, detail="Voting system unavailable")
    normalized_choice = _normalize_connector_vote_choice(choice)
    vote_value = normalized_choice["normalized_vote"]
    species = "human"
    try:
        species = _normalize_species(getattr(actor, "species", None) or "human")
    except HTTPException:
        species = "human"

    existing_vote = db.query(ProposalVote).filter(
        ProposalVote.proposal_id == getattr(proposal, "id"),
        ProposalVote.harmonizer_id == getattr(actor, "id"),
    ).first()

    if existing_vote:
        if hasattr(existing_vote, "vote"):
            existing_vote.vote = vote_value
        if hasattr(existing_vote, "choice"):
            existing_vote.choice = vote_value
        if hasattr(existing_vote, "voter_type"):
            existing_vote.voter_type = species
        if hasattr(existing_vote, "species"):
            existing_vote.species = species
        created = False
    else:
        vote_kwargs = {
            "proposal_id": getattr(proposal, "id"),
            "harmonizer_id": getattr(actor, "id"),
        }
        if hasattr(ProposalVote, "vote"):
            vote_kwargs["vote"] = vote_value
        if hasattr(ProposalVote, "choice"):
            vote_kwargs["choice"] = vote_value
        if hasattr(ProposalVote, "voter_type"):
            vote_kwargs["voter_type"] = species
        if hasattr(ProposalVote, "species"):
            vote_kwargs["species"] = species
        db.add(ProposalVote(**vote_kwargs))
        created = True

    return {
        "proposal_id": getattr(proposal, "id", None),
        "vote": vote_value,
        "intended_choice": normalized_choice["intended_choice"],
        "created": created,
        "actor": getattr(actor, "username", ""),
    }


def _connector_review_rationale(payload: ConnectorDraftAiReviewIn | Dict[str, Any]) -> str:
    if isinstance(payload, dict):
        raw_value = payload.get("rationale") or payload.get("comment") or payload.get("body") or ""
    else:
        raw_value = payload.rationale or payload.comment or payload.body or ""
    rationale = str(raw_value or "").strip()
    if not rationale:
        raise HTTPException(status_code=400, detail="rationale is required")
    if len(rationale) > 800:
        raise HTTPException(status_code=400, detail="rationale must be 800 characters or fewer")
    return rationale


def _connector_confidence(value: Optional[Any]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="confidence must be a number")
    return max(0.0, min(confidence, 1.0))


def _connector_create_ai_review_comment(
    db: Session,
    *,
    actor,
    proposal,
    rationale: str,
    parent_comment_id: Optional[int] = None,
):
    if not CRUD_MODELS_AVAILABLE or Comment is None or VibeNode is None:
        raise HTTPException(status_code=503, detail="Comment system unavailable")

    vibenode_obj = db.query(VibeNode).first()
    if not vibenode_obj:
        vibenode_obj = VibeNode(
            name="default",
            author_id=getattr(actor, "id", None),
        )
        db.add(vibenode_obj)
        db.flush()

    comment_kwargs = {
        "proposal_id": getattr(proposal, "id", None),
        "content": rationale,
        "author_id": getattr(actor, "id", None),
        "vibenode_id": getattr(vibenode_obj, "id", None),
        "created_at": datetime.datetime.utcnow(),
    }
    if parent_comment_id is not None and hasattr(Comment, "parent_comment_id"):
        comment_kwargs["parent_comment_id"] = parent_comment_id
    comment = Comment(**comment_kwargs)
    db.add(comment)
    db.flush()
    return comment


def _connector_create_ai_post(db: Session, *, actor, payload: Dict[str, Any]):
    if not CRUD_MODELS_AVAILABLE or Proposal is None:
        raise HTTPException(status_code=503, detail="Post system unavailable")
    title = str(payload.get("generated_title") or payload.get("title") or "").strip()[:180]
    body = str(payload.get("generated_post_body") or payload.get("body") or "").strip()
    if not title:
        title = f"{getattr(actor, 'username', 'AI delegate')} post"
    if not body:
        raise HTTPException(status_code=400, detail="AI post draft is missing generated content")
    created_at = datetime.datetime.utcnow()
    governance_kind = _normalize_governance_kind(payload.get("governance_kind") or "post")
    decision_level = _normalize_decision_level(payload.get("decision_level") or "standard")
    voting_days = _clamp_voting_days(payload.get("voting_days"))
    voting_deadline = created_at + timedelta(days=voting_days if governance_kind == "decision" else 7)
    proposal_payload = {
        "media_layout": "carousel",
        "ai_authored": True,
        "ai_actor_id": payload.get("ai_actor_id"),
        "ai_actor_username": payload.get("ai_actor_username"),
        "content_hash": payload.get("content_hash"),
        "reasoning_hash": payload.get("reasoning_hash"),
        "generation_source": payload.get("generation_source"),
        "manual_preview_only": True,
    }
    if governance_kind == "decision":
        approval_threshold = _governance_threshold(decision_level)
        proposal_payload.update({
            "governance_kind": "decision",
            "decision_level": decision_level,
            "approval_threshold": approval_threshold,
            "execution_mode": "manual",
            "execution_status": "pending_vote",
            "voting_days": voting_days,
            "voting_deadline": _format_timestamp(voting_deadline),
        })
    username = getattr(actor, "username", "") or payload.get("ai_actor_username") or "ai-delegate"
    avatar_value = getattr(actor, "profile_pic", "") or getattr(actor, "avatar_url", "") or ""
    post = Proposal(
        title=title,
        description=body[:2400],
        userName=username,
        userInitials=(username[:2]).upper() if username else "AI",
        author_id=getattr(actor, "id", None),
        author_type="ai",
        author_img=_social_avatar(avatar_value),
        image="",
        video="",
        link="",
        file="",
        payload=proposal_payload,
        created_at=created_at,
        voting_deadline=voting_deadline,
    )
    db.add(post)
    db.flush()
    return post


@app.get("/connector/actions", summary="List authenticated connector action proposals")
def connector_list_actions(
    status: Optional[str] = Query("draft"),
    limit: Optional[int] = Query(50),
    offset: int = Query(0),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if ConnectorActionProposal is None:
        raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

    actor = get_current_harmonizer(authorization, db)
    clean_status = (status or "draft").strip().lower()
    if clean_status not in CONNECTOR_ACTION_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported connector action status")
    try:
        safe_limit = int(limit if limit is not None else 50)
    except (TypeError, ValueError):
        safe_limit = 50
    safe_limit = max(1, min(safe_limit, 100))
    try:
        safe_offset = int(offset)
    except (TypeError, ValueError):
        safe_offset = 0
    safe_offset = max(0, safe_offset)

    query = (
        db.query(ConnectorActionProposal)
        .filter(ConnectorActionProposal.actor_user_id == getattr(actor, "id", None))
        .filter(ConnectorActionProposal.status == clean_status)
        .order_by(desc(ConnectorActionProposal.created_at), desc(ConnectorActionProposal.id))
    )
    rows = query.offset(safe_offset).limit(safe_limit).all()
    return {
        "ok": True,
        "actions": [_serialize_connector_action(row) for row in rows],
        "count": len(rows),
        "limit": safe_limit,
        "offset": safe_offset,
    }


@app.post("/connector/actions/{action_id}/cancel", summary="Cancel an authenticated draft connector action")
def connector_cancel_action(
    action_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if ConnectorActionProposal is None:
        raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

    actor = get_current_harmonizer(authorization, db)
    action = db.query(ConnectorActionProposal).filter(ConnectorActionProposal.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Connector action proposal not found")
    if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Bearer token does not match connector action actor")
    if getattr(action, "status", "") != "draft":
        raise HTTPException(status_code=409, detail="Only draft connector actions can be canceled")

    try:
        action.status = "canceled"
        db.commit()
        db.refresh(action)
        return {
            "ok": True,
            "action": _serialize_connector_action(action),
            "executed": False,
            "safety": {
                "canceled_only": True,
                "no_write_action_performed": True,
            },
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to cancel connector action: {str(exc)}")


@app.post("/connector/actions/draft-vote", summary="Draft a connector vote action without executing it")
def connector_draft_vote(
    payload: ConnectorDraftVoteIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor = _connector_require_actor(authorization, db, payload.username)
    proposal = _connector_get_proposal_or_404(db, payload.proposal_id)
    choice = _normalize_connector_vote_choice(payload.choice)
    summary = {
        "action": "draft_vote",
        "actor": getattr(actor, "username", ""),
        "proposal_id": getattr(proposal, "id", payload.proposal_id),
        "proposal_title": _connector_proposal_title(proposal),
        **choice,
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_vote",
            actor_user_id=getattr(actor, "id", None),
            target_type="proposal",
            target_id=getattr(proposal, "id", payload.proposal_id),
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft vote action: {str(exc)}")


@app.post("/connector/actions/draft-ai-review", summary="Draft one AI review vote and rationale without executing it")
def connector_draft_ai_review(
    payload: ConnectorDraftAiReviewIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor = _connector_require_ai_actor(authorization, db, payload.username)
    proposal = _connector_get_proposal_or_404(db, payload.proposal_id)
    choice = _normalize_connector_vote_choice(payload.choice)
    rationale = _connector_review_rationale(payload)
    confidence = _connector_confidence(payload.confidence)
    actor_metadata = _ai_delegate_actor_metadata(actor)
    reasoning_hash = _hash_text(rationale)
    summary = {
        "action": "draft_ai_review",
        "actor": getattr(actor, "username", ""),
        "actor_species": "ai",
        **actor_metadata,
        "proposal_id": getattr(proposal, "id", payload.proposal_id),
        "proposal_title": _connector_proposal_title(proposal),
        "rationale": rationale,
        "reasoning_summary": rationale,
        "reasoning_hash": reasoning_hash,
        "confidence": confidence,
        **choice,
        "sealed_reasoning": False,
        "reasoning_source": "ai_actor_submitted_draft",
        "approval_effect": "Publish one AI vote and one AI rationale comment.",
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_ai_review",
            actor_user_id=getattr(actor, "id", None),
            target_type="proposal_ai_review",
            target_id=getattr(proposal, "id", payload.proposal_id),
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft AI review action: {str(exc)}")


@app.post("/connector/actions/draft-ai-delegate-review", summary="Draft a locked-charter AI delegate review without executing it")
def connector_draft_ai_delegate_review(
    payload: ConnectorDraftAiDelegateReviewIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    requester = _connector_require_actor(authorization, db, payload.username)
    proposal = _connector_get_proposal_or_404(db, payload.proposal_id)
    actor_payload = None
    publish_actor = None
    action_actor_user_id = getattr(requester, "id", None)

    if payload.ai_actor_id is not None or payload.ai_actor_username:
        row = (
            _get_ai_actor_row_by_id(db, payload.ai_actor_id)
            if payload.ai_actor_id is not None
            else _get_ai_actor_row_by_username(db, payload.ai_actor_username or "")
        )
        actor_payload = _row_to_ai_actor_payload(row)
        if not actor_payload or actor_payload.get("ai_actor_type") != "principal_delegate":
            raise HTTPException(status_code=404, detail="AI delegate not found")
        if actor_payload.get("custodian_user_id") != getattr(requester, "id", None):
            raise HTTPException(status_code=403, detail="Only the delegate custodian can request this AI review")
        if not actor_payload.get("active"):
            raise HTTPException(status_code=403, detail="AI delegate is disabled")
        publish_actor = db.query(Harmonizer).filter(Harmonizer.id == actor_payload.get("harmonizer_user_id")).first()
        if not publish_actor or (getattr(publish_actor, "species", "") or "").lower() != "ai":
            raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")
        actor_metadata = _ai_delegate_action_metadata(actor_payload)
        actor_metadata["ai_actor_context"] = _build_ai_actor_context(db, actor_payload)
        display_name = actor_payload.get("display_name") or actor_payload.get("username")
    else:
        if (getattr(requester, "species", "") or "").strip().lower() != "ai":
            raise HTTPException(status_code=400, detail="ai_actor_id or ai_actor_username is required")
        publish_actor = requester
        actor_metadata = _ai_delegate_actor_metadata(requester)
        display_name = getattr(requester, "username", "")

    review = _generate_locked_ai_review(
        proposal=proposal,
        actor_payload={
            **actor_metadata,
            "display_name": display_name,
        },
        allow_caution=False,
    )
    choice = _normalize_connector_vote_choice(review["vote_intent"])
    confidence = _connector_confidence(payload.confidence)
    summary = {
        "action": "draft_ai_review",
        "actor": getattr(publish_actor, "username", ""),
        "actor_species": "ai",
        **actor_metadata,
        "approved_by_required_user_id": action_actor_user_id,
        "proposal_id": getattr(proposal, "id", payload.proposal_id),
        "proposal_title": _connector_proposal_title(proposal),
        "rationale": review["reasoning_summary"],
        "reasoning_summary": review["reasoning_summary"],
        "reasoning_text": review["reasoning_text"],
        "reasoning_hash": review["reasoning_hash"],
        "risk_flags": review["risk_flags"],
        "proposal_context": review.get("proposal_context", {}),
        "ai_actor_context": review.get("ai_actor_context", {}),
        "generation_source": review.get("generation_source", "deterministic_fallback_no_key"),
        "model_identity": review.get("model_identity") or actor_metadata.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY,
        "confidence": confidence,
        **choice,
        "sealed_reasoning": True,
        "reasoning_source": "locked_server_charter",
        "approval_effect": "Publish one AI vote and one AI rationale comment.",
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_ai_review",
            actor_user_id=action_actor_user_id,
            target_type="proposal_ai_review",
            target_id=getattr(proposal, "id", payload.proposal_id),
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft AI delegate review action: {str(exc)}")


@app.post("/connector/actions/draft-ai-delegate-comment", summary="Draft a locked-charter AI delegate comment without publishing")
def connector_draft_ai_delegate_comment(
    payload: ConnectorDraftAiDelegateCommentIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    requester = _connector_require_actor(authorization, db, payload.username)
    proposal = _connector_get_proposal_or_404(db, payload.proposal_id)
    focus = _normalize_ai_comment_focus(payload.instruction or payload.focus or "")
    parent_comment_context = None
    parent_comment_id = payload.parent_comment_id
    if parent_comment_id is not None:
        try:
            parent_comment_id = int(parent_comment_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="parent_comment_id must be a comment id")
        if parent_comment_id <= 0:
            raise HTTPException(status_code=400, detail="parent_comment_id must be a comment id")
        parent_comment = db.query(Comment).filter(Comment.id == parent_comment_id).first() if Comment is not None else None
        if not parent_comment:
            raise HTTPException(status_code=404, detail="Reply target comment not found")
        if str(getattr(parent_comment, "proposal_id", "")) != str(getattr(proposal, "id", payload.proposal_id)):
            raise HTTPException(status_code=400, detail="Reply target comment belongs to another post")
        parent_comment_context = _comment_public_context(db, parent_comment)
    row = (
        _get_ai_actor_row_by_id(db, payload.ai_actor_id)
        if payload.ai_actor_id is not None
        else _get_ai_actor_row_by_username(db, payload.ai_actor_username or "")
    )
    actor_payload = _row_to_ai_actor_payload(row)
    if not actor_payload or actor_payload.get("ai_actor_type") != "principal_delegate":
        raise HTTPException(status_code=404, detail="AI delegate not found")
    if actor_payload.get("custodian_user_id") != getattr(requester, "id", None):
        raise HTTPException(status_code=403, detail="Only the delegate custodian can request this AI comment draft")
    if not actor_payload.get("active"):
        raise HTTPException(status_code=403, detail="AI delegate is disabled")
    publish_actor = db.query(Harmonizer).filter(Harmonizer.id == actor_payload.get("harmonizer_user_id")).first()
    if not publish_actor or (getattr(publish_actor, "species", "") or "").lower() != "ai":
        raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")

    actor_metadata = _ai_delegate_action_metadata(actor_payload)
    actor_metadata["ai_actor_context"] = _build_ai_actor_context(db, actor_payload)
    display_name = actor_payload.get("display_name") or actor_payload.get("username")
    comment_draft = _generate_locked_ai_delegate_comment(
        proposal=proposal,
        actor_payload={
            **actor_metadata,
            "display_name": display_name,
        },
        focus=focus,
        parent_comment_context=parent_comment_context,
    )
    summary = {
        "action": "draft_ai_comment",
        "actor": getattr(publish_actor, "username", ""),
        "actor_species": "ai",
        **actor_metadata,
        "approved_by_required_user_id": getattr(requester, "id", None),
        "proposal_id": getattr(proposal, "id", payload.proposal_id),
        "proposal_title": _connector_proposal_title(proposal),
        "parent_comment_id": parent_comment_id,
        "parent_comment_context": parent_comment_context or {},
        "instruction": focus,
        "body": comment_draft["generated_comment"],
        "generated_comment": comment_draft["generated_comment"],
        "content_hash": comment_draft["content_hash"],
        "reasoning_summary": comment_draft["reasoning_summary"],
        "reasoning_text": comment_draft["reasoning_text"],
        "reasoning_hash": comment_draft["reasoning_hash"],
        "proposal_context": comment_draft.get("proposal_context", {}),
        "ai_actor_context": comment_draft.get("ai_actor_context", {}),
        "generation_source": comment_draft.get("generation_source", "deterministic_fallback_no_key"),
        "model_identity": comment_draft.get("model_identity") or actor_metadata.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY,
        "sealed_content": True,
        "content_source": "locked_server_charter",
        "approval_effect": "Publish one AI-authored reply." if parent_comment_id else "Publish one AI-authored comment.",
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_ai_comment",
            actor_user_id=getattr(requester, "id", None),
            target_type="proposal_ai_comment",
            target_id=getattr(proposal, "id", payload.proposal_id),
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft AI delegate comment action: {str(exc)}")


@app.post("/connector/actions/draft-ai-delegate-post", summary="Draft a locked-charter AI delegate post without publishing")
def connector_draft_ai_delegate_post(
    payload: AiDelegatePostDraftIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    requester = _connector_require_actor(authorization, db, payload.username)
    row = (
        _get_ai_actor_row_by_id(db, payload.ai_actor_id)
        if payload.ai_actor_id is not None
        else _get_ai_actor_row_by_username(db, payload.ai_actor_username or "")
    )
    actor_payload = _row_to_ai_actor_payload(row)
    if not actor_payload or actor_payload.get("ai_actor_type") != "principal_delegate":
        raise HTTPException(status_code=404, detail="AI delegate not found")
    if actor_payload.get("custodian_user_id") != getattr(requester, "id", None):
        raise HTTPException(status_code=403, detail="Only the delegate custodian can request this AI post draft")
    if not actor_payload.get("active"):
        raise HTTPException(status_code=403, detail="AI delegate is disabled")
    publish_actor = db.query(Harmonizer).filter(Harmonizer.id == actor_payload.get("harmonizer_user_id")).first()
    if not publish_actor or (getattr(publish_actor, "species", "") or "").lower() != "ai":
        raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")

    actor_metadata = _ai_delegate_action_metadata(actor_payload)
    actor_metadata["ai_actor_context"] = _build_ai_actor_context(db, actor_payload)
    post_draft = _generate_ai_delegate_post_draft(
        actor_payload={
            **actor_metadata,
            "display_name": actor_payload.get("display_name") or actor_payload.get("username"),
        },
        current_text=payload.current_text or "",
        focus=payload.focus or "",
        media_type=payload.media_type or "",
        media_label=payload.media_label or "",
        image_count=payload.image_count or 0,
        image_data_urls=payload.image_data_urls or [],
        governance_kind=payload.governance_kind or "post",
        decision_level=payload.decision_level or "",
        voting_days=payload.voting_days,
    )
    summary = {
        "action": "draft_ai_post",
        "actor": getattr(publish_actor, "username", ""),
        "actor_species": "ai",
        **actor_metadata,
        "approved_by_required_user_id": getattr(requester, "id", None),
        "title": post_draft["generated_title"],
        "body": post_draft["generated_post_body"],
        "generated_title": post_draft["generated_title"],
        "generated_post_body": post_draft["generated_post_body"],
        "content_hash": post_draft["content_hash"],
        "context_hash": post_draft.get("context_hash"),
        "reasoning_summary": post_draft.get("reasoning_summary"),
        "reasoning_text": post_draft.get("reasoning_text"),
        "reasoning_hash": post_draft.get("reasoning_hash"),
        "governance_framing": post_draft.get("governance_framing"),
        "media_caption_guidance": post_draft.get("media_caption_guidance"),
        "ai_actor_context": post_draft.get("ai_actor_context", {}),
        "generation_source": post_draft.get("generation_source", "deterministic_fallback_no_key"),
        "model_identity": post_draft.get("model_identity") or actor_metadata.get("model_identity") or SUPERNOVA_AI_MODEL_IDENTITY,
        "prompt_policy_version": post_draft.get("prompt_policy_version") or actor_metadata.get("prompt_policy_version"),
        "charter_name": post_draft.get("charter_name") or actor_metadata.get("charter_name"),
        "governance_kind": payload.governance_kind or "post",
        "decision_level": payload.decision_level or "",
        "voting_days": payload.voting_days,
        "sealed_content": True,
        "content_source": "locked_server_charter",
        "approval_effect": "Publish one AI-authored post.",
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_ai_post",
            actor_user_id=getattr(requester, "id", None),
            target_type="ai_delegate_post",
            target_id=None,
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft AI delegate post action: {str(exc)}")


@app.post("/connector/actions/{action_id}/approve-vote", summary="Approve and execute a drafted connector vote action")
def connector_approve_vote_action(
    action_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if ConnectorActionProposal is None:
        raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

    actor = get_current_harmonizer(authorization, db)
    action = db.query(ConnectorActionProposal).filter(ConnectorActionProposal.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Connector action proposal not found")
    if getattr(action, "action_type", "") != "draft_vote":
        raise HTTPException(status_code=400, detail="Connector action is not a draft vote")
    if getattr(action, "status", "") != "draft":
        raise HTTPException(status_code=409, detail="Connector action is not in draft status")
    if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Bearer token does not match connector action actor")

    payload = _connector_action_payload(getattr(action, "draft_payload", None))
    proposal_id = payload.get("proposal_id") or getattr(action, "target_id", None)
    try:
        proposal_id = int(proposal_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Connector vote draft is missing proposal_id")

    proposal = _connector_get_proposal_or_404(db, proposal_id)
    choice = payload.get("normalized_vote") or payload.get("intended_choice") or payload.get("choice")
    if not choice:
        raise HTTPException(status_code=400, detail="Connector vote draft is missing vote choice")

    try:
        result = _connector_execute_vote(db, actor=actor, proposal=proposal, choice=choice)
        now = datetime.datetime.utcnow()
        action.status = "executed"
        action.approved_at = now
        action.executed_at = now
        action.result_payload = {
            "proposal_id": result["proposal_id"],
            "vote": result["vote"],
            "intended_choice": result["intended_choice"],
            "actor": result["actor"],
            "created": result["created"],
            "summary": "Connector vote action executed after explicit approval.",
        }
        db.commit()
        db.refresh(action)
        summary = {
            "action": "approve_vote_action",
            "source_action": "draft_vote",
            "actor": getattr(actor, "username", ""),
            "proposal_id": getattr(proposal, "id", proposal_id),
            "proposal_title": _connector_proposal_title(proposal),
            "vote": result["vote"],
            "intended_choice": result["intended_choice"],
        }
        return _connector_action_response(action, summary, action.result_payload)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to approve vote action: {str(exc)}")


@app.post("/connector/actions/{action_id}/approve-ai-review", summary="Approve and publish one AI review vote and rationale")
def connector_approve_ai_review_action(
    action_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if ConnectorActionProposal is None:
        raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

    actor = get_current_harmonizer(authorization, db)
    action = db.query(ConnectorActionProposal).filter(ConnectorActionProposal.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Connector action proposal not found")
    if getattr(action, "action_type", "") != "draft_ai_review":
        raise HTTPException(status_code=400, detail="Connector action is not a draft AI review")
    if getattr(action, "status", "") != "draft":
        raise HTTPException(status_code=409, detail="Connector action is not in draft status")
    payload = _connector_action_payload(getattr(action, "draft_payload", None))
    persistent_ai_actor_id = payload.get("ai_actor_id")
    publish_actor = actor
    if persistent_ai_actor_id is not None and payload.get("delegate_harmonizer_user_id"):
        if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Bearer token does not match AI delegate custodian")
        if payload.get("custodian_id") != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Only the AI delegate custodian can approve this review")
        row = _get_ai_actor_row_by_id(db, persistent_ai_actor_id)
        actor_payload = _row_to_ai_actor_payload(row)
        if not actor_payload or actor_payload.get("custodian_user_id") != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="AI delegate custody no longer matches this action")
        if not actor_payload.get("active"):
            raise HTTPException(status_code=403, detail="AI delegate is disabled")
        publish_actor = db.query(Harmonizer).filter(Harmonizer.id == payload.get("delegate_harmonizer_user_id")).first()
        if not publish_actor or (getattr(publish_actor, "species", "") or "").strip().lower() != "ai":
            raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")
    else:
        if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Bearer token does not match connector action actor")
        if (getattr(actor, "species", "") or "").strip().lower() != "ai":
            raise HTTPException(status_code=403, detail="AI review approval requires an AI actor")

    proposal_id = payload.get("proposal_id") or getattr(action, "target_id", None)
    try:
        proposal_id = int(proposal_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="AI review draft is missing proposal_id")

    proposal = _connector_get_proposal_or_404(db, proposal_id)
    choice = payload.get("normalized_vote") or payload.get("intended_choice") or payload.get("choice")
    if not choice:
        raise HTTPException(status_code=400, detail="AI review draft is missing vote choice")
    rationale = _connector_review_rationale(payload)
    confidence = _connector_confidence(payload.get("confidence"))

    try:
        result = _connector_execute_vote(db, actor=publish_actor, proposal=proposal, choice=choice)
        comment = _connector_create_ai_review_comment(
            db,
            actor=publish_actor,
            proposal=proposal,
            rationale=rationale,
        )
        now = datetime.datetime.utcnow()
        action.status = "executed"
        action.approved_at = now
        action.executed_at = now
        action.result_payload = {
            "proposal_id": result["proposal_id"],
            "vote": result["vote"],
            "intended_choice": result["intended_choice"],
            "actor": result["actor"],
            "comment_id": getattr(comment, "id", None),
            "confidence": confidence,
            "ai_actor_id": payload.get("ai_actor_id"),
            "ai_actor_type": payload.get("ai_actor_type", "principal_delegate"),
            "custody_label": payload.get("custody_label"),
            "model_identity": payload.get("model_identity"),
            "generation_source": payload.get("generation_source"),
            "constitution_hash": payload.get("constitution_hash"),
            "prompt_policy_version": payload.get("prompt_policy_version"),
            "reasoning_hash": payload.get("reasoning_hash") or _hash_text(rationale),
            "reasoning_summary": payload.get("reasoning_summary") or rationale,
            "sealed_reasoning": bool(payload.get("sealed_reasoning")),
            "created_vote": result["created"],
            "executed_action": "ai_review",
            "summary": "AI review published after explicit approval.",
        }
        db.commit()
        db.refresh(action)
        serialized_comment = _serialize_comment_record(db, comment)
        summary = {
            "action": "approve_ai_review_action",
            "source_action": "draft_ai_review",
            "actor": getattr(publish_actor, "username", ""),
            "approved_by": getattr(actor, "username", ""),
            "actor_species": "ai",
            "proposal_id": getattr(proposal, "id", proposal_id),
            "proposal_title": _connector_proposal_title(proposal),
            "vote": result["vote"],
            "intended_choice": result["intended_choice"],
            "comment_id": getattr(comment, "id", None),
            "confidence": confidence,
            "ai_actor_type": action.result_payload.get("ai_actor_type"),
            "reasoning_hash": action.result_payload.get("reasoning_hash"),
            "generation_source": action.result_payload.get("generation_source"),
            "sealed_reasoning": action.result_payload.get("sealed_reasoning"),
            "comment": serialized_comment,
        }
        return _connector_action_response(action, summary, action.result_payload)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to approve AI review action: {str(exc)}")


@app.post("/connector/actions/{action_id}/approve-ai-comment", summary="Approve and publish one AI-authored comment")
def connector_approve_ai_comment_action(
    action_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if ConnectorActionProposal is None:
        raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

    actor = get_current_harmonizer(authorization, db)
    action = db.query(ConnectorActionProposal).filter(ConnectorActionProposal.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Connector action proposal not found")
    if getattr(action, "action_type", "") != "draft_ai_comment":
        raise HTTPException(status_code=400, detail="Connector action is not a draft AI comment")
    if getattr(action, "status", "") != "draft":
        raise HTTPException(status_code=409, detail="Connector action is not in draft status")
    if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Bearer token does not match AI delegate custodian")

    payload = _connector_action_payload(getattr(action, "draft_payload", None))
    if payload.get("custodian_id") != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Only the AI delegate custodian can approve this comment draft")
    persistent_ai_actor_id = payload.get("ai_actor_id")
    row = _get_ai_actor_row_by_id(db, persistent_ai_actor_id)
    actor_payload = _row_to_ai_actor_payload(row)
    if not actor_payload or actor_payload.get("custodian_user_id") != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="AI delegate custody no longer matches this action")
    if not actor_payload.get("active"):
        raise HTTPException(status_code=403, detail="AI delegate is disabled")
    publish_actor = db.query(Harmonizer).filter(Harmonizer.id == payload.get("delegate_harmonizer_user_id")).first()
    if not publish_actor or (getattr(publish_actor, "species", "") or "").strip().lower() != "ai":
        raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")

    proposal_id = payload.get("proposal_id") or getattr(action, "target_id", None)
    try:
        proposal_id = int(proposal_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="AI comment draft is missing proposal_id")
    proposal = _connector_get_proposal_or_404(db, proposal_id)
    body = str(payload.get("generated_comment") or payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="AI comment draft is missing generated content")
    parent_comment_id = payload.get("parent_comment_id")
    if parent_comment_id is not None:
        try:
            parent_comment_id = int(parent_comment_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="AI comment draft has invalid parent_comment_id")
        parent_comment = db.query(Comment).filter(Comment.id == parent_comment_id).first() if Comment is not None else None
        if not parent_comment:
            raise HTTPException(status_code=404, detail="Reply target comment not found")
        if str(getattr(parent_comment, "proposal_id", "")) != str(getattr(proposal, "id", proposal_id)):
            raise HTTPException(status_code=400, detail="Reply target comment belongs to another post")

    try:
        comment = _connector_create_ai_review_comment(
            db,
            actor=publish_actor,
            proposal=proposal,
            rationale=body,
            parent_comment_id=parent_comment_id,
        )
        now = datetime.datetime.utcnow()
        action.status = "executed"
        action.approved_at = now
        action.executed_at = now
        content_hash = payload.get("content_hash") or _hash_text(body)
        action.result_payload = {
            "proposal_id": getattr(proposal, "id", proposal_id),
            "actor": getattr(publish_actor, "username", ""),
            "comment_id": getattr(comment, "id", None),
            "parent_comment_id": parent_comment_id,
            "comment": body,
            "content_hash": content_hash,
            "ai_actor_id": payload.get("ai_actor_id"),
            "ai_actor_type": payload.get("ai_actor_type", "principal_delegate"),
            "custody_label": payload.get("custody_label"),
            "model_identity": payload.get("model_identity"),
            "generation_source": payload.get("generation_source"),
            "constitution_hash": payload.get("constitution_hash"),
            "prompt_policy_version": payload.get("prompt_policy_version"),
            "reasoning_hash": payload.get("reasoning_hash") or _hash_text(body),
            "reasoning_summary": payload.get("reasoning_summary") or "AI-authored comment published.",
            "sealed_content": bool(payload.get("sealed_content")),
            "created_comment": True,
            "executed_action": "ai_comment",
            "summary": "AI-authored comment published after explicit approval.",
        }
        db.commit()
        db.refresh(action)
        serialized_comment = _serialize_comment_record(db, comment)
        summary = {
            "action": "approve_ai_comment_action",
            "source_action": "draft_ai_comment",
            "actor": getattr(publish_actor, "username", ""),
            "approved_by": getattr(actor, "username", ""),
            "actor_species": "ai",
            "proposal_id": getattr(proposal, "id", proposal_id),
            "proposal_title": _connector_proposal_title(proposal),
            "comment_id": getattr(comment, "id", None),
            "parent_comment_id": parent_comment_id,
            "content_hash": content_hash,
            "reasoning_hash": action.result_payload.get("reasoning_hash"),
            "generation_source": action.result_payload.get("generation_source"),
            "sealed_content": action.result_payload.get("sealed_content"),
            "comment": serialized_comment,
        }
        return _connector_action_response(action, summary, action.result_payload)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to approve AI comment action: {str(exc)}")


@app.post("/connector/actions/{action_id}/approve-ai-post", summary="Approve and publish one AI-authored post")
def connector_approve_ai_post_action(
    action_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if ConnectorActionProposal is None:
        raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

    actor = get_current_harmonizer(authorization, db)
    action = db.query(ConnectorActionProposal).filter(ConnectorActionProposal.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Connector action proposal not found")
    if getattr(action, "action_type", "") != "draft_ai_post":
        raise HTTPException(status_code=400, detail="Connector action is not a draft AI post")
    if getattr(action, "status", "") != "draft":
        raise HTTPException(status_code=409, detail="Connector action is not in draft status")
    if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Bearer token does not match AI delegate custodian")

    payload = _connector_action_payload(getattr(action, "draft_payload", None))
    if payload.get("custodian_id") != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Only the AI delegate custodian can approve this post draft")
    persistent_ai_actor_id = payload.get("ai_actor_id")
    row = _get_ai_actor_row_by_id(db, persistent_ai_actor_id)
    actor_payload = _row_to_ai_actor_payload(row)
    if not actor_payload or actor_payload.get("custodian_user_id") != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="AI delegate custody no longer matches this action")
    if not actor_payload.get("active"):
        raise HTTPException(status_code=403, detail="AI delegate is disabled")
    publish_actor = db.query(Harmonizer).filter(Harmonizer.id == payload.get("delegate_harmonizer_user_id")).first()
    if not publish_actor or (getattr(publish_actor, "species", "") or "").strip().lower() != "ai":
        raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")

    try:
        post = _connector_create_ai_post(db, actor=publish_actor, payload=payload)
        _record_proposal_mentions(db, post, getattr(post, "description", "") or "", getattr(post, "userName", ""))
        now = datetime.datetime.utcnow()
        action.status = "executed"
        action.approved_at = now
        action.executed_at = now
        content_hash = payload.get("content_hash") or _hash_text(getattr(post, "description", "") or "")
        action.result_payload = {
            "proposal_id": getattr(post, "id", None),
            "post_id": getattr(post, "id", None),
            "actor": getattr(publish_actor, "username", ""),
            "title": getattr(post, "title", ""),
            "body": getattr(post, "description", ""),
            "content_hash": content_hash,
            "ai_actor_id": payload.get("ai_actor_id"),
            "ai_actor_type": payload.get("ai_actor_type", "principal_delegate"),
            "custody_label": payload.get("custody_label"),
            "model_identity": payload.get("model_identity"),
            "generation_source": payload.get("generation_source"),
            "constitution_hash": payload.get("constitution_hash"),
            "prompt_policy_version": payload.get("prompt_policy_version"),
            "reasoning_hash": payload.get("reasoning_hash") or _hash_text(payload.get("reasoning_summary") or ""),
            "reasoning_summary": payload.get("reasoning_summary") or "AI-authored post published.",
            "sealed_content": bool(payload.get("sealed_content")),
            "created_post": True,
            "executed_action": "ai_post",
            "summary": "AI-authored post published after explicit approval.",
        }
        db.commit()
        db.refresh(action)
        db.refresh(post)
        post_author = getattr(post, "userName", "") or getattr(publish_actor, "username", "")
        post_metadata = _profile_metadata(db, post_author)
        serialized_post = {
            "id": getattr(post, "id", None),
            "title": getattr(post, "title", ""),
            "text": getattr(post, "description", ""),
            "userName": post_author,
            "userInitials": (post_author[:2]).upper() if post_author else "AI",
            "author_img": _social_avatar(getattr(post, "author_img", "") or ""),
            "time": _format_timestamp(getattr(post, "created_at", None)),
            "author_type": "ai",
            "profile_url": post_metadata.get("domain_url", ""),
            "domain_as_profile": bool(post_metadata.get("domain_as_profile", False)),
            "likes": [],
            "dislikes": [],
            "comments": [],
            "media": _media_payload(
                getattr(post, "image", ""),
                getattr(post, "video", ""),
                getattr(post, "link", ""),
                getattr(post, "file", ""),
                getattr(post, "payload", None),
                getattr(post, "voting_deadline", None),
            ),
        }
        summary = {
            "action": "approve_ai_post_action",
            "source_action": "draft_ai_post",
            "actor": getattr(publish_actor, "username", ""),
            "approved_by": getattr(actor, "username", ""),
            "actor_species": "ai",
            "proposal_id": getattr(post, "id", None),
            "post_id": getattr(post, "id", None),
            "title": getattr(post, "title", ""),
            "content_hash": content_hash,
            "reasoning_hash": action.result_payload.get("reasoning_hash"),
            "generation_source": action.result_payload.get("generation_source"),
            "sealed_content": action.result_payload.get("sealed_content"),
            "post": serialized_post,
        }
        return _connector_action_response(action, summary, action.result_payload)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to approve AI post action: {str(exc)}")


@app.post("/connector/actions/draft-comment", summary="Draft a connector comment action without executing it")
def connector_draft_comment(
    payload: ConnectorDraftCommentIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor = _connector_require_actor(authorization, db, payload.username)
    proposal = _connector_get_proposal_or_404(db, payload.proposal_id)
    body = (payload.body or payload.comment or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="comment body is required")
    summary = {
        "action": "draft_comment",
        "actor": getattr(actor, "username", ""),
        "proposal_id": getattr(proposal, "id", payload.proposal_id),
        "proposal_title": _connector_proposal_title(proposal),
        "body": body,
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_comment",
            actor_user_id=getattr(actor, "id", None),
            target_type="proposal",
            target_id=getattr(proposal, "id", payload.proposal_id),
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft comment action: {str(exc)}")


@app.post("/connector/actions/draft-proposal", summary="Draft a connector proposal action without executing it")
def connector_draft_proposal(
    payload: ConnectorDraftProposalIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor = _connector_require_actor(authorization, db, payload.author)
    title = (payload.title or "").strip()
    body = (payload.body or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if not body:
        raise HTTPException(status_code=400, detail="body is required")
    summary = {
        "action": "draft_proposal",
        "actor": getattr(actor, "username", ""),
        "title": title,
        "body": body,
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_proposal",
            actor_user_id=getattr(actor, "id", None),
            target_type="proposal",
            target_id=None,
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft proposal action: {str(exc)}")


@app.post("/connector/actions/draft-collab-request", summary="Draft a connector collab request without executing it")
def connector_draft_collab_request(
    payload: ConnectorDraftCollabRequestIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor = _connector_require_actor(authorization, db, payload.author)
    proposal = _connector_get_proposal_or_404(db, payload.proposal_id)
    owner = _connector_proposal_owner_username(db, proposal)
    if _safe_user_key(owner) != _safe_user_key(getattr(actor, "username", "")):
        raise HTTPException(status_code=403, detail="Only the proposal author can draft a collab request")

    collaborator_username = (payload.collaborator_username or payload.collaborator or "").strip()
    if not collaborator_username:
        raise HTTPException(status_code=400, detail="collaborator username is required")
    collaborator = _find_harmonizer_by_username(db, collaborator_username)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Collaborator not found")

    summary = {
        "action": "draft_collab_request",
        "actor": getattr(actor, "username", ""),
        "proposal_id": getattr(proposal, "id", payload.proposal_id),
        "proposal_title": _connector_proposal_title(proposal),
        "collaborator_username": getattr(collaborator, "username", collaborator_username),
    }
    try:
        record = _create_connector_action_draft(
            db,
            action_type="draft_collab_request",
            actor_user_id=getattr(actor, "id", None),
            target_type="proposal_collab_request",
            target_id=getattr(proposal, "id", payload.proposal_id),
            draft_payload=summary,
        )
        return _connector_draft_response(record, summary)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to draft collab request action: {str(exc)}")


PROPOSAL_COLLAB_ROUTE_STATUSES = {"pending", "approved", "declined", "removed"}
PROPOSAL_COLLAB_ACTIVE_STATUSES = {"pending", "approved"}


def _require_proposal_collabs_available() -> None:
    if ProposalCollab is None or Proposal is None or Harmonizer is None or not CRUD_MODELS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Proposal collabs are unavailable")


def _proposal_collab_limit(value: Optional[int]) -> int:
    try:
        parsed = int(value if value is not None else 50)
    except (TypeError, ValueError):
        parsed = 50
    return max(1, min(parsed, 100))


def _proposal_collab_offset(value: Optional[int]) -> int:
    try:
        parsed = int(value if value is not None else 0)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, parsed)


def _proposal_collab_user_summary(db: Session, user_id: Optional[int]) -> Dict[str, Any]:
    if not user_id or Harmonizer is None:
        return {}
    user = db.query(Harmonizer).filter(Harmonizer.id == user_id).first()
    if not user:
        return {}
    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", ""),
        "species": getattr(user, "species", "human"),
        "avatar": _social_avatar(getattr(user, "profile_pic", "") or getattr(user, "avatar_url", "")),
    }


def _proposal_author_user(db: Session, proposal):
    author_id = getattr(proposal, "author_id", None)
    if author_id and Harmonizer is not None:
        author = db.query(Harmonizer).filter(Harmonizer.id == author_id).first()
        if author:
            return author
    owner_username = _connector_proposal_owner_username(db, proposal)
    return _find_harmonizer_by_username(db, owner_username)


def _serialize_proposal_collab(db: Session, collab) -> Dict[str, Any]:
    proposal = db.query(Proposal).filter(Proposal.id == getattr(collab, "proposal_id", None)).first()
    requested_by = _proposal_collab_user_summary(db, getattr(collab, "requested_by_user_id", None))
    return {
        "id": getattr(collab, "id", None),
        "proposal_id": getattr(collab, "proposal_id", None),
        "proposal_title": _connector_proposal_title(proposal) if proposal else "",
        "author": _proposal_collab_user_summary(db, getattr(collab, "author_user_id", None)),
        "collaborator": _proposal_collab_user_summary(db, getattr(collab, "collaborator_user_id", None)),
        "requested_by": requested_by.get("username", ""),
        "status": getattr(collab, "status", ""),
        "requested_at": _format_timestamp(getattr(collab, "requested_at", None)),
        "responded_at": _format_timestamp(getattr(collab, "responded_at", None)),
        "removed_at": _format_timestamp(getattr(collab, "removed_at", None)),
    }


def _approved_proposal_collabs(db: Session, proposal_id: Optional[int]) -> List[Dict[str, Any]]:
    if not proposal_id or ProposalCollab is None or Harmonizer is None or not CRUD_MODELS_AVAILABLE:
        return []
    try:
        rows = (
            db.query(ProposalCollab)
            .filter(ProposalCollab.proposal_id == proposal_id)
            .filter(ProposalCollab.status == "approved")
            .order_by(ProposalCollab.id.asc())
            .all()
        )
    except Exception:
        return []

    collabs = []
    seen = set()
    for row in rows:
        user = _proposal_collab_user_summary(db, getattr(row, "collaborator_user_id", None))
        username = (user.get("username") or "").strip()
        key = username.lower()
        if not username or key in seen:
            continue
        seen.add(key)
        collabs.append(
            {
                "id": getattr(row, "id", None),
                "username": username,
                "species": user.get("species", "human"),
                "avatar": user.get("avatar", ""),
                "status": "approved",
            }
        )
    return collabs


def _record_proposal_collab_notification(
    db: Session,
    recipient_user_id: Optional[int],
    payload: Dict[str, Any],
) -> None:
    if not recipient_user_id or Notification is None:
        return
    try:
        db.add(
            Notification(
                harmonizer_id=recipient_user_id,
                message=json.dumps(payload, sort_keys=True),
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def _proposal_collab_or_404(db: Session, collab_id: int):
    _require_proposal_collabs_available()
    collab = db.query(ProposalCollab).filter(ProposalCollab.id == collab_id).first()
    if not collab:
        raise HTTPException(status_code=404, detail="Proposal collab not found")
    return collab


@app.post("/proposal-collabs/request", summary="Request a proposal collaborator")
def request_proposal_collab(
    payload: ProposalCollabRequestIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_proposal_collabs_available()
    actor = get_current_harmonizer(authorization, db)
    proposal = _connector_get_proposal_or_404(db, payload.proposal_id)
    author = _proposal_author_user(db, proposal)
    if not author or getattr(author, "id", None) != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Only the proposal author can request a collab")

    collaborator_username = (payload.collaborator_username or "").strip()
    if not collaborator_username:
        raise HTTPException(status_code=400, detail="collaborator username is required")
    collaborator = _find_harmonizer_by_username(db, collaborator_username)
    if not collaborator:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    if getattr(collaborator, "id", None) == getattr(author, "id", None):
        raise HTTPException(status_code=400, detail="Cannot request self-collab")

    duplicate = (
        db.query(ProposalCollab)
        .filter(ProposalCollab.proposal_id == getattr(proposal, "id", None))
        .filter(ProposalCollab.collaborator_user_id == getattr(collaborator, "id", None))
        .filter(ProposalCollab.status.in_(sorted(PROPOSAL_COLLAB_ACTIVE_STATUSES)))
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Active proposal collab already exists")

    collab = ProposalCollab(
        proposal_id=getattr(proposal, "id", payload.proposal_id),
        author_user_id=getattr(author, "id"),
        collaborator_user_id=getattr(collaborator, "id"),
        requested_by_user_id=getattr(actor, "id"),
        status="pending",
    )
    try:
        db.add(collab)
        db.commit()
        db.refresh(collab)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to request proposal collab: {str(exc)}")

    _record_proposal_collab_notification(
        db,
        getattr(collaborator, "id", None),
        {
            "type": "collab_request",
            "source_type": "proposal_collab",
            "collab_id": getattr(collab, "id", None),
            "proposal_id": getattr(proposal, "id", None),
            "title": "Collab request",
            "actor": getattr(author, "username", ""),
            "recipient": getattr(collaborator, "username", ""),
            "body": f"{getattr(author, 'username', 'Someone')} invited you to collaborate on a post",
        },
    )
    collab = db.query(ProposalCollab).filter(ProposalCollab.id == getattr(collab, "id", None)).first()
    return {"ok": True, "collab": _serialize_proposal_collab(db, collab)}


@app.get("/proposal-collabs", summary="List authenticated proposal collab requests")
def list_proposal_collabs(
    status: Optional[str] = Query("pending"),
    role: Optional[str] = Query("collaborator"),
    limit: Optional[int] = Query(50),
    offset: Optional[int] = Query(0),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_proposal_collabs_available()
    actor = get_current_harmonizer(authorization, db)
    clean_status = (status or "pending").strip().lower()
    if clean_status not in PROPOSAL_COLLAB_ROUTE_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported proposal collab status")
    clean_role = (role or "collaborator").strip().lower()
    if clean_role not in {"collaborator", "author"}:
        raise HTTPException(status_code=400, detail="Unsupported proposal collab role")

    safe_limit = _proposal_collab_limit(limit)
    safe_offset = _proposal_collab_offset(offset)
    user_id = getattr(actor, "id", None)
    query = db.query(ProposalCollab).filter(ProposalCollab.status == clean_status)
    if clean_role == "author":
        query = query.filter(ProposalCollab.author_user_id == user_id)
    else:
        query = query.filter(ProposalCollab.collaborator_user_id == user_id)
    rows = (
        query.order_by(desc(ProposalCollab.requested_at), desc(ProposalCollab.id))
        .offset(safe_offset)
        .limit(safe_limit)
        .all()
    )
    return {
        "ok": True,
        "collabs": [_serialize_proposal_collab(db, row) for row in rows],
        "count": len(rows),
        "limit": safe_limit,
        "offset": safe_offset,
        "role": clean_role,
        "status": clean_status,
    }


def _proposal_collab_transition(
    collab_id: int,
    authorization: Optional[str],
    db: Session,
    *,
    next_status: str,
):
    actor = get_current_harmonizer(authorization, db)
    collab = _proposal_collab_or_404(db, collab_id)
    if getattr(collab, "collaborator_user_id", None) != getattr(actor, "id", None):
        raise HTTPException(status_code=403, detail="Only the requested collaborator can respond")
    if getattr(collab, "status", "") != "pending":
        raise HTTPException(status_code=409, detail="Only pending proposal collabs can be updated")

    try:
        collab.status = next_status
        collab.responded_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(collab)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update proposal collab: {str(exc)}")

    notification_type = "collab_approved" if next_status == "approved" else "collab_declined"
    notification_title = "Collab approved" if next_status == "approved" else "Collab declined"
    _record_proposal_collab_notification(
        db,
        getattr(collab, "author_user_id", None),
        {
            "type": notification_type,
            "source_type": "proposal_collab",
            "collab_id": getattr(collab, "id", None),
            "proposal_id": getattr(collab, "proposal_id", None),
            "title": notification_title,
            "actor": getattr(actor, "username", ""),
            "status": next_status,
        },
    )
    collab = db.query(ProposalCollab).filter(ProposalCollab.id == collab_id).first()
    return {"ok": True, "collab": _serialize_proposal_collab(db, collab)}


@app.post("/proposal-collabs/{collab_id}/approve", summary="Approve a pending proposal collab")
def approve_proposal_collab(
    collab_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    return _proposal_collab_transition(
        collab_id,
        authorization,
        db,
        next_status="approved",
    )


@app.post("/proposal-collabs/{collab_id}/decline", summary="Decline a pending proposal collab")
def decline_proposal_collab(
    collab_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    return _proposal_collab_transition(
        collab_id,
        authorization,
        db,
        next_status="declined",
    )


@app.post("/proposal-collabs/{collab_id}/remove", summary="Remove a proposal collab association")
def remove_proposal_collab(
    collab_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    actor = get_current_harmonizer(authorization, db)
    collab = _proposal_collab_or_404(db, collab_id)
    actor_id = getattr(actor, "id", None)
    if actor_id not in {getattr(collab, "author_user_id", None), getattr(collab, "collaborator_user_id", None)}:
        raise HTTPException(status_code=403, detail="Only the proposal author or collaborator can remove a collab")
    if getattr(collab, "status", "") == "removed":
        raise HTTPException(status_code=409, detail="Proposal collab is already removed")
    if getattr(collab, "status", "") not in {"pending", "approved", "declined"}:
        raise HTTPException(status_code=409, detail="Proposal collab cannot be removed in its current status")

    recipient_id = (
        getattr(collab, "collaborator_user_id", None)
        if actor_id == getattr(collab, "author_user_id", None)
        else getattr(collab, "author_user_id", None)
    )
    try:
        collab.status = "removed"
        collab.removed_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(collab)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to remove proposal collab: {str(exc)}")

    _record_proposal_collab_notification(
        db,
        recipient_id,
        {
            "type": "collab_removed",
            "source_type": "proposal_collab",
            "collab_id": getattr(collab, "id", None),
            "proposal_id": getattr(collab, "proposal_id", None),
            "title": "Collab removed",
            "actor": getattr(actor, "username", ""),
            "status": "removed",
        },
    )
    collab = db.query(ProposalCollab).filter(ProposalCollab.id == collab_id).first()
    return {"ok": True, "collab": _serialize_proposal_collab(db, collab)}


@app.get("/.well-known/webfinger", summary="Discover a public SuperNova profile")
def webfinger(resource: str = Query(...), db: Session = Depends(get_db)):
    username = _username_from_webfinger_resource(resource)
    if not _profile_exists(db, username):
        raise HTTPException(status_code=404, detail="Profile not found")
    identity = _profile_identity_payload(db, username)
    aliases = [identity["local_profile_url"]]
    if identity.get("domain_url"):
        aliases.append(identity["domain_url"])
    payload = {
        "subject": f"acct:{identity['username']}@{urlparse(PUBLIC_BASE_URL).netloc or '2177.tech'}",
        "aliases": aliases,
        "links": [
            {
                "rel": "self",
                "type": "application/activity+json",
                "href": identity["actor_url"],
            },
            {
                "rel": "http://webfinger.net/rel/profile-page",
                "href": identity["local_profile_url"],
            },
            {
                "rel": "https://supernova2177.org/rel/portable-profile",
                "type": "application/json",
                "href": identity["portable_export_url"],
            },
        ],
    }
    return JSONResponse(
        payload,
        media_type="application/jrd+json",
        headers=PUBLIC_FEDERATION_CACHE_HEADERS,
    )


@app.get("/actors/{username}", summary="Read-only ActivityStreams actor profile")
def actor_profile(username: str, db: Session = Depends(get_db)):
    if not _profile_exists(db, username):
        raise HTTPException(status_code=404, detail="Profile not found")
    identity = _profile_identity_payload(db, username)
    species = (identity.get("species") or "human").lower()
    actor_type = "Organization" if species == "company" else "Service" if species == "ai" else "Person"
    actor: Dict[str, Any] = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": identity["actor_url"],
        "type": actor_type,
        "preferredUsername": identity["username"],
        "name": identity["display_name"],
        "summary": identity.get("bio", ""),
        "url": identity["canonical_url"],
        "outbox": f"{identity['actor_url']}/outbox",
        "supernova": {
            "species": identity["species"],
            "local_profile_url": identity["local_profile_url"],
            "claimed_domain": identity["claimed_domain"],
            "domain_url": identity["domain_url"],
            "domain_as_profile": identity["domain_as_profile"],
            "domain_verified": identity["domain_verified"],
            "verified_domain": identity["verified_domain"],
            "did": identity["did"],
        },
    }
    if identity.get("avatar_url"):
        actor["icon"] = {"type": "Image", "url": identity["avatar_url"]}
    if identity.get("domain_url"):
        actor["alsoKnownAs"] = [identity["domain_url"]]
    return JSONResponse(
        actor,
        media_type="application/activity+json",
        headers=PUBLIC_FEDERATION_CACHE_HEADERS,
    )


@app.get("/actors/{username}/outbox", summary="Read-only public proposal outbox")
def actor_outbox(
    username: str,
    limit: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if not _profile_exists(db, username):
        raise HTTPException(status_code=404, detail="Profile not found")
    identity = _profile_identity_payload(db, username)
    proposals = list_proposals(
        filter="latest",
        search=None,
        author=identity["username"],
        before_id=None,
        limit=limit,
        offset=0,
        db=db,
    )
    items = []
    for item in proposals:
        pid = item.get("id")
        object_url = f"{PUBLIC_BASE_URL}/proposals/{pid}"
        items.append({
            "id": f"{object_url}#create",
            "type": "Create",
            "actor": identity["actor_url"],
            "object": {
                "id": object_url,
                "type": "Note",
                "attributedTo": identity["actor_url"],
                "name": item.get("title", ""),
                "content": item.get("text", ""),
                "url": object_url,
            },
        })
    return JSONResponse(
        {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"{identity['actor_url']}/outbox",
            "type": "OrderedCollection",
            "totalItems": len(items),
            "orderedItems": items,
        },
        media_type="application/activity+json",
        headers=PUBLIC_FEDERATION_CACHE_HEADERS,
    )


@app.get("/api/users/{username}/portable-profile", summary="Export a public portable profile")
@app.get("/u/{username}/export.json", summary="Export a public portable profile")
def portable_profile(
    username: str,
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if not _profile_exists(db, username):
        raise HTTPException(status_code=404, detail="Profile not found")
    identity = _profile_identity_payload(db, username)
    public_posts = list_proposals(
        filter="latest",
        search=None,
        author=identity["username"],
        before_id=None,
        limit=limit,
        offset=0,
        db=db,
    )
    return JSONResponse({
        "schema": "supernova.portable_profile.v1",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "identity": identity,
        "profile": profile(identity["username"], db),
        "public_posts": public_posts,
        "governance": {
            "species_model": "three_species_equal_vote",
            "human_supervision_required": True,
            "execution_current_mode": "manual_preview_only",
            "automatic_execution": False,
        },
        "privacy": {
            "public_export_only": True,
            "excluded_fields": [
                "email",
                "password_hash",
                "access_token",
                "refresh_token",
                "direct_messages",
                "private_message_metadata",
                "secrets",
                "admin_state",
                "debug_state",
            ],
        },
        "limits": {"public_posts": limit},
    }, headers=PUBLIC_FEDERATION_CACHE_HEADERS)


@app.patch("/profile/{username}", summary="Update a user profile")
def update_profile(
    username: str,
    payload: ProfileUpdateIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if Harmonizer is None:
        raise HTTPException(status_code=503, detail="User system unavailable")

    clean_username = username.strip()
    if not clean_username:
        raise HTTPException(status_code=400, detail="Username is required")
    _require_token_identity_match(authorization, db, clean_username)

    user = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == clean_username.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_username = user.username
    next_username = old_username
    if payload.username is not None:
        candidate_username = payload.username.strip()
        if not candidate_username:
            raise HTTPException(status_code=400, detail="Username is required")
        if len(candidate_username) > 80:
            raise HTTPException(status_code=400, detail="Username is too long")
        existing_user = (
            db.query(Harmonizer)
            .filter(func.lower(Harmonizer.username) == candidate_username.lower())
            .first()
        )
        if existing_user and getattr(existing_user, "id", None) != getattr(user, "id", None):
            raise HTTPException(status_code=409, detail="Username is already taken")
        user.username = candidate_username
        next_username = candidate_username

    avatar_to_sync = ""
    if payload.avatar_url is not None:
        avatar_url = payload.avatar_url.strip()
        if avatar_url:
            user.profile_pic = avatar_url
            avatar_to_sync = avatar_url
        elif _is_default_avatar(getattr(user, "profile_pic", "")):
            user.profile_pic = "default.jpg"

    old_species = getattr(user, "species", "human") or "human"
    species_changed = False
    if payload.species is not None:
        next_species = _normalize_public_account_species(payload.species)
        species_changed = next_species != old_species
        user.species = next_species

    if payload.bio is not None:
        user.bio = payload.bio.strip()[:500]

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = getattr(user, "id", None)
        username_changed = _safe_user_key(old_username) != _safe_user_key(next_username)
        if _safe_user_key(old_username) != _safe_user_key(next_username):
            _sync_username_references(old_username, next_username, user_id)
            _sync_ai_delegate_custodian_prefix(db, old_username, next_username, user_id)
            _rename_profile_metadata(db, old_username, next_username)
            _record_username_alias(db, old_username, next_username, user_id)
            db.commit()
        if payload.domain_url is not None or payload.domain_as_profile is not None:
            _upsert_profile_metadata(db, next_username, payload.domain_url, payload.domain_as_profile)
        avatar_value = avatar_to_sync
        if not avatar_value and username_changed:
            current_avatar = getattr(user, "profile_pic", "") or ""
            if current_avatar and not _is_default_avatar(current_avatar):
                avatar_value = current_avatar
        if avatar_value:
            _sync_user_avatar_references(
                db,
                user.username,
                avatar_value,
                user_id,
                aliases=[old_username, next_username],
            )
        if species_changed or username_changed:
            _sync_species_references(
                user.username,
                getattr(user, "species", "human") or "human",
                user_id,
                aliases=[old_username, next_username],
            )
        response_payload = _public_user_payload(user, provider="password")
        response_payload.update(_auth_fields_for_user(user))
        response_payload.update(_profile_metadata(db, next_username))
        return response_payload
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")


app.include_router(create_social_graph_router(
    get_db=get_db,
    follow_model=FollowIn,
    collect_social_users=_collect_social_users,
    profile_metadata=_profile_metadata,
    safe_user_key=_safe_user_key,
    social_avatar=_social_avatar,
    find_harmonizer_by_username=_find_harmonizer_by_username,
    read_follows_store=_read_follows_store,
    write_follows_store=_write_follows_store,
    enforce_token_identity_match=lambda *args, **kwargs: _enforce_token_identity_match(*args, **kwargs),
    require_token_identity_match=lambda *args, **kwargs: _require_token_identity_match(*args, **kwargs),
    proposal_model=Proposal,
    comment_model=Comment,
    proposal_vote_model=ProposalVote,
    crud_models_available=CRUD_MODELS_AVAILABLE,
    serialize_comment_record=_serialize_comment_record,
    serialize_vote_record=_serialize_vote_record,
))


app.include_router(create_messages_router(
    get_db=get_db,
    direct_message_model=DirectMessageIn,
    safe_user_key=_safe_user_key,
    require_token_identity_match=lambda *args, **kwargs: _require_token_identity_match(*args, **kwargs),
    canonical_username_from_alias=_canonical_username_from_alias,
    conversation_id=_conversation_id,
    ensure_direct_messages_table=_ensure_direct_messages_table,
    message_payload=_message_payload,
    read_messages_store=_read_messages_store,
    write_messages_store=_write_messages_store,
))


@app.post(
    "/proposals",
    response_model=ProposalSchema,
    response_model_exclude={"collabs"},
    summary="Create a new proposal",
)
async def create_proposal(
    title: str = Form(...),
    body: str = Form(...),
    author: str = Form(...),
    author_type: str = Form("human"),
    author_img: str = Form(""),
    date: Optional[str] = Form(None),
    video: str = Form(""),
    link: str = Form(""),
    media_layout: str = Form("carousel"),
    image: Optional[UploadFile] = File(None),
    images: Optional[List[UploadFile]] = File(None),
    video_file: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    voting_deadline: Optional[datetime.datetime] = Form(None),
    governance_kind: str = Form("post"),
    decision_level: str = Form("standard"),
    voting_days: Optional[int] = Form(None),
    execution_mode: str = Form("manual"),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db)
):
    if author_type not in ("human", "company", "ai"):
        raise HTTPException(status_code=400, detail="Invalid author_type")
    _require_token_identity_match(authorization, db, author)
    
    os.makedirs(uploads_dir, exist_ok=True)
    image_filename = None
    image_filenames = []
    video_value = video or ""
    file_filename = None
    safe_media_layout = _normalize_media_layout(media_layout)
    safe_governance_kind = _normalize_governance_kind(governance_kind)
    safe_decision_level = _normalize_decision_level(decision_level)
    safe_voting_days = _clamp_voting_days(voting_days)
    safe_execution_mode = "manual" if str(execution_mode or "").strip().lower() != "manual" else "manual"

    # --- Process uploads ---
    image_uploads = []
    if image:
        image_uploads.append(image)
    if images:
        image_uploads.extend([item for item in images if item])
    for image_upload in image_uploads:
        if not _upload_matches(image_upload, "image/", IMAGE_UPLOAD_EXTENSIONS):
            raise HTTPException(status_code=400, detail="Uploaded image files must be images")
        next_filename = _save_upload_file(
            image_upload,
            IMAGE_UPLOAD_EXTENSIONS,
            ".jpg",
            UPLOAD_IMAGE_MAX_BYTES,
        )
        image_filenames.append(next_filename)
    if len(image_filenames) == 1:
        image_filename = image_filenames[0]
    elif len(image_filenames) > 1:
        image_filename = json.dumps(image_filenames)

    if video_file:
        if not _upload_matches(video_file, "video/", VIDEO_UPLOAD_EXTENSIONS):
            raise HTTPException(status_code=400, detail="Uploaded video file must be a video")
        video_filename = _save_upload_file(
            video_file,
            VIDEO_UPLOAD_EXTENSIONS,
            ".mp4",
            UPLOAD_VIDEO_MAX_BYTES,
        )
        video_value = video_filename
    
    if file:
        if _safe_upload_extension(file) not in DOCUMENT_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Uploaded file type is not supported")
        file_filename = _save_upload_file(
            file,
            DOCUMENT_UPLOAD_EXTENSIONS,
            max_bytes=UPLOAD_DOCUMENT_MAX_BYTES,
        )

    from datetime import datetime as dt
    if date:
        normalized_date = date.replace("Z", "+00:00")
        created_at = dt.fromisoformat(normalized_date)
    else:
        created_at = dt.utcnow()
    if not voting_deadline:
        deadline_days = safe_voting_days if safe_governance_kind == "decision" else 7
        voting_deadline = created_at + timedelta(days=deadline_days)
    proposal_payload = {"media_layout": safe_media_layout}
    if safe_governance_kind == "decision":
        approval_threshold = _governance_threshold(safe_decision_level)
        proposal_payload.update({
            "governance_kind": "decision",
            "decision_level": safe_decision_level,
            "approval_threshold": approval_threshold,
            "execution_mode": safe_execution_mode,
            "execution_status": "pending_vote",
            "voting_days": safe_voting_days,
            "voting_deadline": _format_timestamp(voting_deadline),
        })

    try:
        final_user = None
        if author and author.strip():
            final_user = author.strip()
        if 'userName' in locals() and userName and userName.strip():
            final_user = userName.strip()
        if not final_user:
            final_user = "Unknown"
        initials = (final_user[:2].upper() if final_user else "UN")
        author_obj = None
        if Harmonizer is not None and final_user:
            author_obj = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == final_user.lower()).first()
            account_species = getattr(author_obj, "species", None) if author_obj else None
            if account_species in ("human", "company", "ai"):
                author_type = account_species

        if CRUD_MODELS_AVAILABLE:
            if author_obj:
                user_name = author_obj.username
            else:
                user_name = final_user
            db_proposal = Proposal(
                title=title,
                description=body,
                userName=user_name,
                userInitials=(user_name[:2]).upper() if user_name else "UN",
                author_type=author_type,
                author_img=author_img,
                image=image_filename,
                video=video_value,
                link=link,
                file=file_filename,
                payload=proposal_payload,
                created_at=created_at,
                voting_deadline=voting_deadline
            )
            db.add(db_proposal)
            db.commit()
            db.refresh(db_proposal)
        else:
            insert_params = {
                "title": title,
                "description": body,
                "userName": final_user,
                "userInitials": initials,
                "author_type": author_type,
                "author_img": author_img,
                "created_at": created_at,
                "voting_deadline": voting_deadline,
                "image": image_filename,
                "video": video_value,
                "link": link,
                "file": file_filename,
                "payload": json.dumps(proposal_payload),
            }
            try:
                result = db.execute(
                    text("""
                        INSERT INTO proposals (
                            title, description, userName, userInitials, author_type,
                            author_img, created_at, voting_deadline, image, video, link, file, payload
                        )
                        VALUES (
                            :title, :description, :userName, :userInitials, :author_type,
                            :author_img, :created_at, :voting_deadline, :image, :video, :link, :file, :payload
                        )
                        RETURNING id
                    """),
                    insert_params,
                )
            except Exception:
                db.rollback()
                result = db.execute(
                    text("""
                        INSERT INTO proposals (
                            title, description, userName, userInitials, author_type,
                            author_img, created_at, voting_deadline, image, video, link, file
                        )
                        VALUES (
                            :title, :description, :userName, :userInitials, :author_type,
                            :author_img, :created_at, :voting_deadline, :image, :video, :link, :file
                        )
                        RETURNING id
                    """),
                    insert_params,
                )
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="Failed to create proposal")
            db.commit()
            db_proposal = type("Temp", (), {})()
            db_proposal.id = row[0]
            db_proposal.title = title
            db_proposal.description = body
            db_proposal.userName = final_user
            db_proposal.userInitials = initials
            db_proposal.author_type = author_type
            db_proposal.author_img = author_img
            db_proposal.image = image_filename
            db_proposal.video = video_value
            db_proposal.link = link
            db_proposal.file = file_filename
            db_proposal.payload = proposal_payload
            db_proposal.created_at = created_at
            db_proposal.voting_deadline = voting_deadline
            user_name = final_user

        _record_proposal_mentions(db, db_proposal, body, user_name)
        author_metadata = _profile_metadata(db, user_name)
        return ProposalSchema(
            id=db_proposal.id,
            title=db_proposal.title,
            text=db_proposal.description,
            userName=user_name,
            userInitials=(user_name[:2]).upper() if user_name else "UN",
            author_img=db_proposal.author_img or "",
            time=_format_timestamp(db_proposal.created_at),
            author_type=db_proposal.author_type,
            profile_url=author_metadata.get("domain_url", ""),
            domain_as_profile=bool(author_metadata.get("domain_as_profile", False)),
            likes=[],
            dislikes=[],
            comments=[],
            media=_media_payload(
                db_proposal.image,
                db_proposal.video,
                db_proposal.link,
                db_proposal.file,
                getattr(db_proposal, "payload", None),
                getattr(db_proposal, "voting_deadline", None),
            )
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create proposal: {str(e)}")
#
# --- Harmonizer serialization helper ---
def serialize_harmonizer(h):
    if not h:
        return None
    avatar_value = getattr(h, "profile_pic", "") or getattr(h, "avatar_url", "") or ""
    # Only select safe fields for serialization
    return {
        "id": getattr(h, "id", None),
        "username": getattr(h, "username", None),
        "avatar_url": _social_avatar(avatar_value),
        "species": getattr(h, "species", None),
        "karma_score": float(getattr(h, "karma_score", 0)) if hasattr(h, "karma_score") else 0,
        "harmony_score": float(getattr(h, "harmony_score", 0)) if hasattr(h, "harmony_score") else 0,
        "creative_spark": float(getattr(h, "creative_spark", 0)) if hasattr(h, "creative_spark") else 0,
    }


def get_current_harmonizer(
    authorization: Optional[str], db: Session
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if jwt is None:
        raise HTTPException(status_code=500, detail="JWT support is unavailable")

    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    username = payload.get("sub")
    if not username or Harmonizer is None:
        raise HTTPException(status_code=401, detail="User not found")

    user = None
    token_user_id = payload.get("uid")
    if token_user_id is not None:
        try:
            user = db.query(Harmonizer).filter(Harmonizer.id == int(token_user_id)).first()
        except (TypeError, ValueError):
            user = None
    if not user:
        user = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == str(username).lower()).first()
    if not user:
        alias = _resolve_username_alias(db, username)
        if alias:
            alias_user_id = alias.get("user_id")
            if alias_user_id is not None:
                try:
                    user = db.query(Harmonizer).filter(Harmonizer.id == int(alias_user_id)).first()
                except (TypeError, ValueError):
                    user = None
            if not user and alias.get("new_username"):
                user = db.query(Harmonizer).filter(
                    func.lower(Harmonizer.username) == str(alias.get("new_username")).lower()
                ).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _optional_current_harmonizer(authorization: Optional[str], db: Session):
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return get_current_harmonizer(authorization, db)
    except HTTPException:
        # Compatibility-first: legacy sessions may have non-JWT fallback tokens.
        # Only enforce conflicts when a token can be resolved to a real account.
        return None


def _enforce_token_identity_match(
    authorization: Optional[str],
    db: Session,
    *identity_values: Optional[str],
):
    current_user = _optional_current_harmonizer(authorization, db)
    if not current_user:
        return None
    token_key = _safe_user_key(getattr(current_user, "username", ""))
    for value in identity_values:
        value_key = _safe_user_key(value or "")
        if value_key and value_key != token_key:
            alias = _resolve_username_alias(db, value)
            alias_matches_user = bool(
                alias
                and (
                    _safe_user_key(alias.get("new_username") or "") == token_key
                    or (alias.get("user_id") is not None and alias.get("user_id") == getattr(current_user, "id", None))
                )
            )
            if alias_matches_user:
                continue
            raise HTTPException(status_code=403, detail="Bearer token does not match requested user")
    return current_user


def _require_token_identity_match(
    authorization: Optional[str],
    db: Session,
    *identity_values: Optional[str],
):
    current_user = get_current_harmonizer(authorization, db)
    token_key = _safe_user_key(getattr(current_user, "username", ""))
    for value in identity_values:
        value_key = _safe_user_key(value or "")
        if value_key and value_key != token_key:
            alias = _resolve_username_alias(db, value)
            alias_matches_user = bool(
                alias
                and (
                    _safe_user_key(alias.get("new_username") or "") == token_key
                    or (alias.get("user_id") is not None and alias.get("user_id") == getattr(current_user, "id", None))
                )
            )
            if alias_matches_user:
                continue
            raise HTTPException(status_code=403, detail="Bearer token does not match requested user")
    return current_user


@app.get("/users/me")
def read_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    current_user = get_current_harmonizer(authorization, db)
    return serialize_harmonizer(current_user)

@app.get("/proposals", response_model=List[ProposalSchema])
def list_proposals(
    filter: str = Query("all"),
    search: Optional[str] = Query(None),
    author: Optional[str] = Query(None),
    before_id: Optional[int] = Query(None, ge=1),
    limit: int = Query(80, ge=1, le=200),
    offset: int = Query(0, ge=0),
    embedded_comments_limit: Optional[int] = Query(None),
    embedded_votes_limit: Optional[int] = Query(None),
    include_collabs: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    List proposals, supporting filters:
    - all, latest, oldest, topLikes, fewestLikes, popular, ai, company, human
    - search: string search on title/description/username
    """
    try:
        _ensure_proposal_read_indexes(db)
        has_comment_cap = embedded_comments_limit is not None
        has_vote_cap = embedded_votes_limit is not None
        safe_comment_cap = max(0, min(int(embedded_comments_limit), 500)) if has_comment_cap else None
        safe_vote_cap = max(0, min(int(embedded_votes_limit), 500)) if has_vote_cap else None

        # --- ORM MODE ---
        if CRUD_MODELS_AVAILABLE:
            from sqlalchemy import func, case
            query = db.query(Proposal)
            clean_author = (author or "").strip()
            author_collab_user_id = None
            approved_collab_proposal_ids: List[int] = []
            if include_collabs and clean_author and ProposalCollab is not None and Harmonizer is not None:
                try:
                    author_collab_user_id = getattr(_find_harmonizer_by_username(db, clean_author), "id", None)
                except Exception:
                    author_collab_user_id = None
                if author_collab_user_id is not None:
                    try:
                        approved_collab_proposal_ids = [
                            int(row[0])
                            for row in (
                                db.query(ProposalCollab.proposal_id)
                                .filter(ProposalCollab.status == "approved")
                                .filter(ProposalCollab.collaborator_user_id == author_collab_user_id)
                                .all()
                            )
                            if row and row[0] is not None
                        ]
                    except Exception:
                        approved_collab_proposal_ids = []

            def apply_author_scope(base_query):
                if not clean_author:
                    return base_query
                author_conditions = [func.lower(Proposal.userName) == clean_author.lower()]
                if author_collab_user_id is not None:
                    author_conditions.append(Proposal.author_id == author_collab_user_id)
                if approved_collab_proposal_ids:
                    author_conditions.append(Proposal.id.in_(approved_collab_proposal_ids))
                return base_query.filter(or_(*author_conditions))

            # SEARCH
            if search and search.strip():
                search_filter = f"%{search}%"
                query = query.filter(
                    or_(
                        Proposal.title.ilike(search_filter),
                        Proposal.description.ilike(search_filter),
                        Proposal.userName.ilike(search_filter)
                    )
                )
            query = apply_author_scope(query)
            if before_id:
                query = query.filter(Proposal.id < before_id)

            # FILTERS
            filter = (filter or "all").lower()
            # Sorting/Filtering logic
            if filter == "latest":
                query = query.order_by(desc(Proposal.created_at))
            elif filter == "oldest":
                query = query.order_by(asc(Proposal.created_at))
            elif filter == "toplikes":
                vote_count = func.sum(case((ProposalVote.vote == "up", 1), else_=0)).label("upvote_count")
                query = query.outerjoin(ProposalVote, Proposal.id == ProposalVote.proposal_id)\
                    .group_by(Proposal.id)\
                    .order_by(desc(vote_count))
            elif filter == "fewestlikes":
                vote_count = func.sum(case((ProposalVote.vote == "up", 1), else_=0)).label("upvote_count")
                query = query.outerjoin(ProposalVote, Proposal.id == ProposalVote.proposal_id)\
                    .group_by(Proposal.id)\
                    .order_by(asc(vote_count))
            elif filter == "popular":
                from datetime import datetime, timedelta
                since = datetime.utcnow() - timedelta(days=1)
                vote_count = func.sum(case((ProposalVote.vote == "up", 1), else_=0)).label("upvote_count")
                query = db.query(Proposal, vote_count)\
                          .outerjoin(ProposalVote, Proposal.id == ProposalVote.proposal_id)\
                          .filter(Proposal.created_at >= since)
                if search and search.strip():
                    search_filter = f"%{search.strip()}%"
                    query = query.filter(
                        or_(
                            Proposal.title.ilike(search_filter),
                            Proposal.description.ilike(search_filter),
                            Proposal.userName.ilike(search_filter)
                            )
                    )
                query = apply_author_scope(query)
                if before_id:
                    query = query.filter(Proposal.id < before_id)
                query = query.group_by(Proposal.id).order_by(desc(vote_count))
                proposals = [p for p, _ in query.offset(offset).limit(limit).all()]
            elif filter == "ai":
                query = query.filter(Proposal.author_type == "ai").order_by(desc(Proposal.created_at))
            elif filter == "company":
                query = query.filter(Proposal.author_type == "company").order_by(desc(Proposal.created_at))
            elif filter == "human":
                query = query.filter(Proposal.author_type == "human").order_by(desc(Proposal.created_at))
            else:
                # Default: all, order by id desc
                query = query.order_by(desc(Proposal.id))

            if filter != "popular":
                proposals = query.offset(offset).limit(limit).all()

        # --- FALLBACK (RAW SQL) ---
        else:
            filter_sql = (filter or "all").lower()
            base_query = "SELECT * FROM proposals"
            where_clauses = []
            order_clause = "ORDER BY id DESC"
            votes_table_exists = False
            comments_table_exists = False

            try:
                table_rows = db.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
                existing_tables = {row[0] for row in table_rows}
                votes_table_exists = "proposal_votes" in existing_tables
                comments_table_exists = "comments" in existing_tables
            except Exception:
                pass

            # SEARCH
            params = {}
            if search and search.strip():
                where_clauses.append(
                    "(LOWER(title) LIKE LOWER(:search) OR LOWER(description) LIKE LOWER(:search) OR LOWER(userName) LIKE LOWER(:search))"
                )
                params["search"] = f"%{search}%"
            if author and author.strip():
                if include_collabs and "proposal_collabs" in existing_tables and "harmonizers" in existing_tables:
                    where_clauses.append(
                        "("
                        "LOWER(userName) = LOWER(:author) "
                        "OR id IN ("
                        "SELECT pc.proposal_id FROM proposal_collabs pc "
                        "JOIN harmonizers h ON h.id = pc.collaborator_user_id "
                        "WHERE pc.status = 'approved' AND LOWER(h.username) = LOWER(:author)"
                        ")"
                        ")"
                    )
                else:
                    where_clauses.append("LOWER(userName) = LOWER(:author)")
                params["author"] = author.strip()
            if before_id:
                where_clauses.append("id < :before_id")
                params["before_id"] = before_id

            # FILTERS
            if filter_sql == "latest":
                order_clause = "ORDER BY created_at DESC"
            elif filter_sql == "oldest":
                order_clause = "ORDER BY created_at ASC"
            elif filter_sql == "ai":
                where_clauses.append("author_type = 'ai'")
            elif filter_sql == "company":
                where_clauses.append("author_type = 'company'")
            elif filter_sql == "human":
                where_clauses.append("author_type = 'human'")
            # For topLikes, fewestLikes, popular, fallback: order by likes/dislikes if possible
            elif filter_sql in ("toplikes", "fewestlikes", "popular"):
                # For fallback, try to join votes table if exists
                # We assume a "votes" table with proposal_id, choice ('up'/'down')
                if filter_sql == "toplikes":
                    base_query = """
                        SELECT p.*, COUNT(v.proposal_id) AS upvotes
                        FROM proposals p
                        LEFT JOIN proposal_votes v ON p.id = v.proposal_id AND v.vote = 'up'
                        GROUP BY p.id
                        ORDER BY upvotes DESC
                    """
                    order_clause = ""
                elif filter_sql == "fewestlikes":
                    base_query = """
                        SELECT p.*, COUNT(v.proposal_id) AS upvotes
                        FROM proposals p
                        LEFT JOIN proposal_votes v ON p.id = v.proposal_id AND v.vote = 'up'
                        GROUP BY p.id
                        ORDER BY upvotes ASC
                    """
                    order_clause = ""
                elif filter_sql == "popular":
                    base_query = """
                        SELECT p.*, COUNT(v.proposal_id) AS total_votes
                        FROM proposals p
                        LEFT JOIN proposal_votes v ON p.id = v.proposal_id
                        GROUP BY p.id
                        ORDER BY total_votes DESC
                    """
                    order_clause = ""

            # Compose query
            if "GROUP BY" not in base_query:
                if where_clauses:
                    base_query += " WHERE " + " AND ".join(where_clauses)
                if order_clause:
                    base_query += f" {order_clause}"
            base_query += " LIMIT :limit OFFSET :offset"
            params["limit"] = limit
            params["offset"] = offset
            proposals = db.execute(text(base_query), params).fetchall()

        # --- SERIALIZATION ---
        proposals_list = []
        profile_metadata_cache: Dict[str, Dict[str, Any]] = {}
        for prop in proposals:
            if CRUD_MODELS_AVAILABLE:
                user_name = ""
                author_obj = None
                if hasattr(prop, "author_id") and prop.author_id:
                    author_obj = db.query(Harmonizer).filter(Harmonizer.id == prop.author_id).first()
                    if author_obj and hasattr(author_obj, "username"):
                        user_name = author_obj.username
                if not user_name:
                    # fallback para userName, author_username, author, "Unknown"
                    if hasattr(prop, "userName") and prop.userName:
                        user_name = prop.userName
                    elif hasattr(prop, "author_username") and prop.author_username:
                        user_name = prop.author_username
                    elif hasattr(prop, "author") and prop.author:
                        user_name = prop.author
                    else:
                        user_name = "Unknown"
                if author_obj is None:
                    author_obj = _find_harmonizer_by_username(db, user_name)
                user_initials = (user_name[:2].upper() if user_name else "UN")
            else:
                user_name = getattr(prop, "userName", None) or getattr(prop, "author", None) or "Unknown"
                author_obj = _find_harmonizer_by_username(db, user_name)
                user_initials = (user_name[:2].upper() if user_name else "UN")

            # Votes and Comments
            if CRUD_MODELS_AVAILABLE:
                vote_query = db.query(ProposalVote).filter(ProposalVote.proposal_id == prop.id)
                if has_vote_cap:
                    vote_query = vote_query.order_by(ProposalVote.harmonizer_id.asc()).limit(safe_vote_cap)
                votes = vote_query.all()

                comment_query = db.query(Comment).filter(Comment.proposal_id == prop.id)
                if has_comment_cap:
                    comment_query = comment_query.order_by(Comment.id.asc()).limit(safe_comment_cap)
                comments = comment_query.all()
            else:
                # fallback: try to get from votes and comments tables
                if votes_table_exists:
                    if has_vote_cap:
                        votes = db.execute(
                            text(
                                "SELECT * FROM proposal_votes WHERE proposal_id = :pid "
                                "ORDER BY harmonizer_id ASC LIMIT :limit"
                            ),
                            {"pid": prop.id, "limit": safe_vote_cap},
                        ).fetchall()
                    else:
                        votes = db.execute(
                            text("SELECT * FROM proposal_votes WHERE proposal_id = :pid"),
                            {"pid": prop.id},
                        ).fetchall()
                else:
                    votes = []
                if comments_table_exists:
                    if has_comment_cap:
                        comments = db.execute(
                            text(
                                "SELECT * FROM comments WHERE proposal_id = :pid "
                                "ORDER BY id ASC LIMIT :limit"
                            ),
                            {"pid": prop.id, "limit": safe_comment_cap},
                        ).fetchall()
                    else:
                        comments = db.execute(
                            text("SELECT * FROM comments WHERE proposal_id = :pid"),
                            {"pid": prop.id},
                        ).fetchall()
                else:
                    comments = []

            # Likes/Dislikes
            likes = []
            dislikes = []
            for v in votes:
                like_entry, dislike_entry = _serialize_vote_record(db, v)
                if like_entry:
                    likes.append(like_entry)
                if dislike_entry:
                    dislikes.append(dislike_entry)

            # Comments
            comments_list = []
            if CRUD_MODELS_AVAILABLE or comments_table_exists:
                for c in comments:
                    comments_list.append(_serialize_comment_record(db, c))

            author_img = getattr(prop, "author_img", "")
            if author_obj is not None:
                author_img = getattr(author_obj, "profile_pic", None) or author_img
            author_key = _safe_user_key(user_name)
            if author_key not in profile_metadata_cache:
                profile_metadata_cache[author_key] = _profile_metadata(db, user_name)
            author_metadata = profile_metadata_cache.get(author_key, {})

            proposals_list.append({
                "id": prop.id,
                "title": getattr(prop, "title", ""),
                "userName": str(user_name),
                "userInitials": user_initials,
                "text": getattr(prop, "description", "") if SUPER_NOVA_AVAILABLE else getattr(prop, "body", None) or getattr(prop, "description", ""),
                "author_img": _social_avatar(author_img),
                "time": _format_timestamp(getattr(prop, "created_at", None) or getattr(prop, "date", "")),
                "author_type": getattr(prop, "author_type", "human"),
                "profile_url": author_metadata.get("domain_url", ""),
                "domain_as_profile": bool(author_metadata.get("domain_as_profile", False)),
                "likes": likes,
                "dislikes": dislikes,
                "comments": comments_list,
                "collabs": _approved_proposal_collabs(db, prop.id),
                "media": _media_payload(
                    getattr(prop, "image", ""),
                    getattr(prop, "video", ""),
                    getattr(prop, "link", ""),
                    getattr(prop, "file", ""),
                    getattr(prop, "payload", None),
                    getattr(prop, "voting_deadline", None),
                )
            })

        return proposals_list

    except Exception as e:
        import traceback
        print(f"Error in list_proposals: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to list proposals: {str(e)}")

#
#
# --- Dedicated yes/no system vote ---
@app.get("/system-vote")
def get_system_vote(username: Optional[str] = Query(None), db: Session = Depends(get_db)):
    try:
        _ensure_system_votes_table(db)
        rows = db.execute(
            text("SELECT username, choice, voter_type FROM system_votes ORDER BY updated_at DESC")
        ).fetchall()
        return _serialize_system_vote_rows(rows, username)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to load system vote: {str(exc)}")


@app.get("/system-vote/config")
def get_system_vote_config():
    return {
        "question": SYSTEM_VOTE_QUESTION,
        "deadline": SYSTEM_VOTE_DEADLINE,
    }


@app.post("/system-vote")
def cast_system_vote(
    payload: SystemVoteIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    username = (payload.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    choice = _normalize_system_vote_choice(payload.choice)
    _require_token_identity_match(authorization, db, username)
    _enforce_system_vote_deadline()
    voter_type = _species_for_username(db, username, payload.voter_type)
    now = datetime.datetime.utcnow()

    try:
        _ensure_system_votes_table(db)
        db.execute(
            text("DELETE FROM system_votes WHERE lower(username) = lower(:username)"),
            {"username": username},
        )
        db.execute(
            text(
                "INSERT INTO system_votes (username, choice, voter_type, created_at, updated_at) "
                "VALUES (:username, :choice, :voter_type, :created_at, :updated_at)"
            ),
            {
                "username": username,
                "choice": choice,
                "voter_type": voter_type,
                "created_at": now,
                "updated_at": now,
            },
        )
        db.commit()
        rows = db.execute(
            text("SELECT username, choice, voter_type FROM system_votes ORDER BY updated_at DESC")
        ).fetchall()
        return _serialize_system_vote_rows(rows, username)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to cast system vote: {str(exc)}")


@app.delete("/system-vote")
def remove_system_vote(
    username: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    requester = (username or "").strip()
    if not requester:
        raise HTTPException(status_code=400, detail="username is required")
    _require_token_identity_match(authorization, db, requester)
    try:
        _ensure_system_votes_table(db)
        db.execute(
            text("DELETE FROM system_votes WHERE lower(username) = lower(:username)"),
            {"username": requester},
        )
        db.commit()
        rows = db.execute(
            text("SELECT username, choice, voter_type FROM system_votes ORDER BY updated_at DESC")
        ).fetchall()
        return _serialize_system_vote_rows(rows, requester)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to remove system vote: {str(exc)}")


# --- Tally endpoints ---
# REMOVE DUPLICATE get_proposal ENDPOINT
    
@app.get("/proposals/{pid}/tally-weighted")
def tally_weighted(pid: int):
    if not SUPER_NOVA_AVAILABLE:
        raise HTTPException(status_code=501, detail="SuperNova weighted voting not available")
    return tally_votes(pid)

# --- Decision endpoint ---
@app.post("/decide/{pid}", response_model=DecisionSchema)
def decide(pid: int, threshold: float = 0.6, db: Session = Depends(get_db)):
    try:
        # Sistema ponderado
        weighted_decision = None
        if CRUD_MODELS_AVAILABLE:
            try:
                level = "important" if threshold >= 0.9 else "standard"
                weighted_decision = weighted_decide(pid, level)
                status = weighted_decision.get("status", "undecided")
            except Exception as e:
                print(f"Weighted decision failed: {e}")
        
        # Fallback para sistema tradicional
        if not weighted_decision:
            tally_result = _compute_vote_totals(db, pid)
            total = tally_result["up"] + tally_result["down"]
            status = "rejected"
            if total > 0 and (tally_result["up"] / total) >= threshold:
                status = "accepted"
        
        #
        if CRUD_MODELS_AVAILABLE:
            existing = db.query(Decision).filter(Decision.proposal_id == pid).first()
            if existing:
                existing.status = status
            else:
                decision = Decision(proposal_id=pid, status=status)
                db.add(decision)
        else:
            existing = db.execute(
                text("SELECT * FROM decisions WHERE proposal_id = :pid"),
                {"pid": pid}
            ).fetchone()
            
            if existing:
                db.execute(
                    text("UPDATE decisions SET status = :status WHERE id = :id"),
                    {"status": status, "id": existing.id}
                )
            else:
                db.execute(
                    text("INSERT INTO decisions (proposal_id, status) VALUES (:pid, :status)"),
                    {"pid": pid, "status": status}
                )
        
        db.commit()
        
        #
        if CRUD_MODELS_AVAILABLE:
            decision_obj = db.query(Decision).filter(Decision.proposal_id == pid).first()
            return DecisionSchema(
                id=decision_obj.id,
                proposal_id=decision_obj.proposal_id,
                status=decision_obj.status
            )
        else:
            decision_obj = db.execute(
                text("SELECT * FROM decisions WHERE proposal_id = :pid"),
                {"pid": pid}
            ).fetchone()
            return DecisionSchema(
                id=decision_obj.id,
                proposal_id=decision_obj.proposal_id,
                status=decision_obj.status
            )
            
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save decision: {str(e)}")


def _stored_notification_payload(notification) -> Dict[str, Any]:
    raw_message = getattr(notification, "message", "") or ""
    created_at = getattr(notification, "created_at", None)
    base: Dict[str, Any] = {
        "id": f"notification-{getattr(notification, 'id', '')}",
        "type": "notification",
        "title": raw_message or "Notification",
        "time": _format_timestamp(created_at),
    }
    try:
        parsed = json.loads(raw_message)
    except Exception:
        return base
    if not isinstance(parsed, dict):
        return base

    payload = {**base, **parsed}
    payload["id"] = f"notification-{getattr(notification, 'id', '')}"
    payload["type"] = parsed.get("type") or base["type"]
    payload["title"] = parsed.get("title") or base["title"]
    payload["time"] = parsed.get("time") or base["time"]
    return payload


def _add_persisted_notifications_for_user(
    db: Session,
    username: str,
    items: List[Dict[str, Any]],
    limit: int,
) -> None:
    remaining = max(0, limit - len(items))
    if (
        remaining <= 0
        or not username
        or not CRUD_MODELS_AVAILABLE
        or Harmonizer is None
        or Notification is None
    ):
        return

    recipient = (
        db.query(Harmonizer)
        .filter(func.lower(Harmonizer.username) == username.lower())
        .first()
    )
    if not recipient:
        return

    notifications = (
        db.query(Notification)
        .filter(Notification.harmonizer_id == recipient.id)
        .order_by(desc(Notification.created_at), desc(Notification.id))
        .limit(remaining)
        .all()
    )
    for notification in notifications:
        items.append(_stored_notification_payload(notification))


def _notification_excerpt(value: str, limit: int = 240) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "..."


def _record_mention_notifications(
    db: Session,
    source_text: str,
    author_username: str,
    *,
    source_type: str,
    proposal_id: Optional[int] = None,
    comment_id: Optional[int] = None,
    title: str,
) -> List[str]:
    if (
        parse_mentions is None
        or Notification is None
        or Harmonizer is None
        or not CRUD_MODELS_AVAILABLE
    ):
        return []

    mention_tokens = parse_mentions(source_text, author_username=author_username)
    if not mention_tokens:
        return []

    created_for: List[str] = []
    for token in mention_tokens:
        mentioned_user = (
            db.query(Harmonizer)
            .filter(func.lower(Harmonizer.username) == token.normalized)
            .first()
        )
        if not mentioned_user:
            continue

        notification_payload = {
            "type": "mention",
            "source_type": source_type,
            "proposal_id": proposal_id,
            "comment_id": comment_id,
            "title": title,
            "actor": author_username,
            "mentioned_user": getattr(mentioned_user, "username", ""),
            "body": _notification_excerpt(source_text),
        }
        db.add(
            Notification(
                harmonizer_id=mentioned_user.id,
                message=json.dumps(notification_payload, sort_keys=True),
            )
        )
        created_for.append(getattr(mentioned_user, "username", ""))

    return created_for


def _record_proposal_mentions(
    db: Session,
    proposal,
    proposal_text: str,
    author_username: str,
) -> List[str]:
    if proposal is None:
        return []

    try:
        created_for = _record_mention_notifications(
            db,
            proposal_text,
            author_username,
            source_type="proposal",
            proposal_id=getattr(proposal, "id", None),
            title="Mentioned you in a post",
        )
        if created_for:
            db.commit()
        return created_for
    except Exception:
        db.rollback()
        return []


@app.get("/notifications")
def list_notifications(
    user: Optional[str] = Query(None),
    limit: int = Query(12, ge=1, le=30),
    db: Session = Depends(get_db),
):
    clean_user = (user or "").strip()
    items: List[Dict[str, Any]] = []
    _ensure_comment_thread_columns(db)

    def add_recent_posts() -> None:
        remaining = max(0, limit - len(items))
        if remaining <= 0:
            return
        try:
            if Proposal is not None:
                for proposal in db.query(Proposal).order_by(desc(Proposal.id)).limit(remaining).all():
                    proposal_id = getattr(proposal, "id", None)
                    items.append({
                        "id": f"post-{proposal_id}",
                        "type": "post",
                        "proposal_id": proposal_id,
                        "title": getattr(proposal, "title", None) or "New proposal",
                        "actor": getattr(proposal, "userName", None) or "SuperNova",
                        "time": _format_timestamp(getattr(proposal, "created_at", None)),
                    })
                return
        except Exception:
            pass
        try:
            rows = db.execute(
                text("SELECT id, title, userName, created_at FROM proposals ORDER BY id DESC LIMIT :limit"),
                {"limit": remaining},
            ).fetchall()
            for row in rows:
                data = getattr(row, "_mapping", row)
                items.append({
                    "id": f"post-{data['id']}",
                    "type": "post",
                    "proposal_id": data["id"],
                    "title": data["title"] or "New proposal",
                    "actor": data["userName"] or "SuperNova",
                    "time": _format_timestamp(data["created_at"]),
                })
        except Exception:
            pass

    if clean_user:
        try:
            _add_persisted_notifications_for_user(db, clean_user, items, limit)
            if CRUD_MODELS_AVAILABLE:
                owned_comment_rows = (
                    db.query(Comment.id)
                    .join(Harmonizer, Comment.author_id == Harmonizer.id)
                    .filter(func.lower(Harmonizer.username) == clean_user.lower())
                    .limit(500)
                    .all()
                )
                owned_comment_ids = [row[0] for row in owned_comment_rows if row[0]]
                if owned_comment_ids:
                    replies = (
                        db.query(Comment)
                        .filter(Comment.parent_comment_id.in_(owned_comment_ids))
                        .order_by(desc(Comment.created_at))
                        .limit(limit)
                        .all()
                    )
                    for reply in replies:
                        payload = _serialize_comment_record(db, reply)
                        if _safe_user_key(payload.get("user", "")) == _safe_user_key(clean_user):
                            continue
                        proposal_title = "Reply to your comment"
                        if Proposal is not None and payload.get("proposal_id"):
                            proposal = db.query(Proposal).filter(Proposal.id == payload["proposal_id"]).first()
                            proposal_title = getattr(proposal, "title", None) or proposal_title
                        items.append({
                            "id": f"comment-reply-{payload.get('id')}",
                            "type": "comment_reply",
                            "proposal_id": payload.get("proposal_id"),
                            "comment_id": payload.get("id"),
                            "parent_comment_id": payload.get("parent_comment_id"),
                            "title": proposal_title,
                            "actor": payload.get("user") or "Someone",
                            "body": payload.get("comment") or "",
                            "time": payload.get("created_at") or "",
                        })
            else:
                rows = db.execute(
                    text("""
                        SELECT r.id, r.proposal_id, r.parent_comment_id, r.user, r.comment, r.created_at,
                               p.title AS proposal_title
                        FROM comments r
                        JOIN comments parent ON r.parent_comment_id = parent.id
                        LEFT JOIN proposals p ON p.id = r.proposal_id
                        WHERE lower(parent.user) = lower(:user)
                          AND lower(COALESCE(r.user, '')) != lower(:user)
                        ORDER BY r.created_at DESC
                        LIMIT :limit
                    """),
                    {"user": clean_user, "limit": limit},
                ).fetchall()
                for row in rows:
                    data = getattr(row, "_mapping", row)
                    items.append({
                        "id": f"comment-reply-{data['id']}",
                        "type": "comment_reply",
                        "proposal_id": data["proposal_id"],
                        "comment_id": data["id"],
                        "parent_comment_id": data["parent_comment_id"],
                        "title": data["proposal_title"] or "Reply to your comment",
                        "actor": data["user"] or "Someone",
                        "body": data["comment"] or "",
                        "time": _format_timestamp(data["created_at"]),
                    })
        except Exception:
            db.rollback()

    add_recent_posts()
    return items[:limit]


# --- Comment endpoint ---
@app.get("/comments")
def list_comments(
    proposal_id: int,
    limit: Optional[int] = Query(None),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    _ensure_comment_thread_columns(db)
    has_pagination = limit is not None
    safe_limit = max(1, min(int(limit), 500)) if has_pagination else None
    safe_offset = max(0, int(offset or 0))
    if CRUD_MODELS_AVAILABLE:
        query = db.query(Comment).filter(Comment.proposal_id == proposal_id)
        if has_pagination:
            query = query.order_by(Comment.id.asc()).offset(safe_offset).limit(safe_limit)
        comments = query.all()
        return [_serialize_comment_record(db, comment) for comment in comments]

    if has_pagination:
        result = db.execute(
            text(
                "SELECT * FROM comments WHERE proposal_id = :pid "
                "ORDER BY id ASC LIMIT :limit OFFSET :offset"
            ),
            {"pid": proposal_id, "limit": safe_limit, "offset": safe_offset},
        )
    else:
        result = db.execute(
            text("SELECT * FROM comments WHERE proposal_id = :pid"),
            {"pid": proposal_id},
        )
    return [_serialize_comment_record(db, comment) for comment in result.fetchall()]


def _record_comment_mentions(
    db: Session,
    comment,
    comment_text: str,
    author_username: str,
) -> List[str]:
    if (
        not CRUD_MODELS_AVAILABLE
        or comment is None
        or parse_mentions is None
        or Notification is None
        or Harmonizer is None
    ):
        return []

    mention_tokens = parse_mentions(comment_text, author_username=author_username)
    if not mention_tokens:
        return []

    try:
        created_for: List[str] = []
        current_mentions = {
            _safe_user_key(getattr(user, "username", ""))
            for user in getattr(comment, "mentions", []) or []
        }
        for token in mention_tokens:
            mentioned_user = (
                db.query(Harmonizer)
                .filter(func.lower(Harmonizer.username) == token.normalized)
                .first()
            )
            if not mentioned_user:
                continue

            mentioned_key = _safe_user_key(getattr(mentioned_user, "username", ""))
            if not mentioned_key or mentioned_key in current_mentions:
                continue

            if hasattr(comment, "mentions"):
                comment.mentions.append(mentioned_user)
                current_mentions.add(mentioned_key)

            notification_payload = {
                "type": "mention",
                "proposal_id": getattr(comment, "proposal_id", None),
                "comment_id": getattr(comment, "id", None),
                "title": "Mentioned you in a comment",
                "actor": author_username,
                "mentioned_user": getattr(mentioned_user, "username", ""),
                "body": comment_text or "",
            }
            db.add(
                Notification(
                    harmonizer_id=mentioned_user.id,
                    message=json.dumps(notification_payload, sort_keys=True),
                )
            )
            created_for.append(getattr(mentioned_user, "username", ""))

        if created_for:
            db.add(comment)
            db.commit()
    except Exception:
        db.rollback()
        return []

    return created_for


@app.post("/comments")
def add_comment(
    c: CommentIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    import datetime
    try:
        _require_token_identity_match(authorization, db, c.user)
        _ensure_comment_thread_columns(db)
        # --- 1. Obter ou criar Harmonizer ---
        author_obj = db.query(Harmonizer).filter(Harmonizer.username == c.user).first() if CRUD_MODELS_AVAILABLE else None
        if CRUD_MODELS_AVAILABLE and not author_obj:
            author_obj = Harmonizer(
                username=c.user,
                email=f"{c.user}@example.com",
                hashed_password="fallback",
                species=c.species or "human",
                profile_pic="default.jpg",
                created_at=datetime.datetime.utcnow(),
                is_active=True,
                is_admin=False,
                harmony_score=0.0,
                creative_spark=0.0,
                karma_score=0.0,
                network_centrality=0.0,
                last_passive_aura_timestamp=datetime.datetime.utcnow(),
                consent_given=True,
                bio=""
            )
            db.add(author_obj)
            db.commit()
            db.refresh(author_obj)

        species_value = getattr(author_obj, "species", c.species or "human") if author_obj else (c.species or "human")

        # --- 2. Obter ou criar VibeNode ---
        vibenode_id = None
        if CRUD_MODELS_AVAILABLE:
            vibenode_obj = db.query(VibeNode).first()
            if not vibenode_obj:
                vibenode_obj = VibeNode(
                    name="default",
                    author_id=author_obj.id if author_obj else 1
                )
                db.add(vibenode_obj)
                db.commit()
                db.refresh(vibenode_obj)
            vibenode_id = vibenode_obj.id

        # --- 3. Criar Comment ---
        comments_list = []
        if CRUD_MODELS_AVAILABLE:
            if author_obj and author_obj.id and vibenode_id:
                # Atualizar profile_pic se frontend enviou imagem
                if c.user_img and c.user_img.strip():
                    author_obj.profile_pic = c.user_img
                    db.add(author_obj)
                    db.commit()
                    db.refresh(author_obj)

                comment = Comment(
                    proposal_id=c.proposal_id,
                    content=c.comment,
                    author_id=author_obj.id,
                    vibenode_id=vibenode_id,
                    parent_comment_id=c.parent_comment_id,
                    created_at=datetime.datetime.utcnow()
                )
                db.add(comment)
                db.commit()
                db.refresh(comment)
                _record_comment_mentions(db, comment, c.comment, c.user)
                # Serializar comment com profile_pic somente se não for "default.jpg"
                comments_list = [_serialize_comment_record(db, comment)]
        else:
            user_img_value = c.user_img if c.user_img else ""
            created_at = datetime.datetime.utcnow()
            insert_payload = {
                "pid": c.proposal_id,
                "user": c.user or "Anonymous",
                "user_img": user_img_value,
                "comment": c.comment,
                "parent_comment_id": c.parent_comment_id,
                "created_at": created_at,
            }
            inserted_id = None
            try:
                inserted = db.execute(
                    text(
                        "INSERT INTO comments (proposal_id, user, user_img, comment, parent_comment_id, created_at) "
                        "VALUES (:pid, :user, :user_img, :comment, :parent_comment_id, :created_at) RETURNING id"
                    ),
                    insert_payload,
                ).fetchone()
                inserted_id = getattr(inserted, "id", None) if inserted else None
            except Exception:
                db.rollback()
                db.execute(
                    text("INSERT INTO comments (proposal_id, user, user_img, comment) VALUES (:pid, :user, :user_img, :comment)"),
                    insert_payload,
                )
                latest = db.execute(
                    text(
                        "SELECT id FROM comments WHERE proposal_id = :pid AND user = :user "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    insert_payload,
                ).fetchone()
                inserted_id = getattr(latest, "id", None) if latest else None
            db.commit()
            comments_list = [{
                "id": inserted_id,
                "proposal_id": c.proposal_id,
                "user": c.user or "Anonymous",
                "user_img": user_img_value,
                "species": c.species or "human",
                "comment": c.comment,
                "parent_comment_id": c.parent_comment_id,
                "created_at": _format_timestamp(created_at),
            }]

        return {
            "ok": True,
            "species": species_value,
            "comments": comments_list
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import traceback
        print("Failed to add comment:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to add comment: {str(e)}")


@app.patch("/comments/{comment_id}")
def update_comment(
    comment_id: int,
    payload: CommentUpdateIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    next_comment = (payload.comment or "").strip()
    if not _safe_user_key(payload.user):
        raise HTTPException(status_code=400, detail="user is required")
    if not next_comment:
        raise HTTPException(status_code=400, detail="comment is required")
    current_user = _require_token_identity_match(authorization, db, payload.user)
    requester = _safe_user_key(getattr(current_user, "username", "") or payload.user)

    try:
        if CRUD_MODELS_AVAILABLE:
            comment = db.query(Comment).filter(Comment.id == comment_id).first()
            if not comment:
                raise HTTPException(status_code=404, detail="Comment not found")

            comment_author = ""
            if getattr(comment, "author", None) is not None:
                comment_author = getattr(comment.author, "username", "") or ""
            elif getattr(comment, "author_id", None):
                author_obj = db.query(Harmonizer).filter(Harmonizer.id == comment.author_id).first()
                comment_author = getattr(author_obj, "username", "") if author_obj else ""

            if requester != _safe_user_key(comment_author):
                raise HTTPException(status_code=403, detail="Only the comment author can edit this comment")

            comment.content = next_comment
            db.commit()
            db.refresh(comment)
            return _serialize_comment_record(db, comment)

        row = db.execute(
            text("SELECT * FROM comments WHERE id = :comment_id"),
            {"comment_id": comment_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")

        comment_author = getattr(row, "user", "") or ""
        if requester != _safe_user_key(comment_author):
            raise HTTPException(status_code=403, detail="Only the comment author can edit this comment")

        db.execute(
            text("UPDATE comments SET comment = :comment WHERE id = :comment_id"),
            {"comment": next_comment, "comment_id": comment_id},
        )
        db.commit()
        updated = db.execute(
            text("SELECT * FROM comments WHERE id = :comment_id"),
            {"comment_id": comment_id},
        ).fetchone()
        return _serialize_comment_record(db, updated)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to edit comment: {str(exc)}")


@app.post("/comments/{comment_id}/votes")
def vote_comment(
    comment_id: int,
    payload: CommentVoteIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    username = (payload.username or "").strip()
    choice = (payload.choice or "").strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    if choice not in {"up", "down"}:
        raise HTTPException(status_code=400, detail="choice must be up or down")
    current_user = _require_token_identity_match(authorization, db, username)
    username = getattr(current_user, "username", "") or username

    try:
        _ensure_comment_votes_table(db)
        if CRUD_MODELS_AVAILABLE:
            comment = db.query(Comment).filter(Comment.id == comment_id).first()
            if not comment:
                raise HTTPException(status_code=404, detail="Comment not found")
            if _is_deleted_comment_record(comment):
                raise HTTPException(status_code=400, detail="Cannot vote on a deleted comment")
            harmonizer = db.query(Harmonizer).filter(Harmonizer.id == getattr(current_user, "id", None)).first()
            if not harmonizer:
                harmonizer = db.query(Harmonizer).filter(func.lower(Harmonizer.username) == username.lower()).first()
            if not harmonizer:
                raise HTTPException(status_code=404, detail=f"User '{username}' not found")
            voter_type = getattr(harmonizer, "species", None) or payload.voter_type or "human"
            harmonizer_id = getattr(harmonizer, "id", None)
        else:
            row = db.execute(text("SELECT * FROM comments WHERE id = :comment_id"), {"comment_id": comment_id}).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Comment not found")
            if _is_deleted_comment_record(row):
                raise HTTPException(status_code=400, detail="Cannot vote on a deleted comment")
            harmonizer = db.query(Harmonizer).filter(Harmonizer.id == getattr(current_user, "id", None)).first() if Harmonizer is not None else None
            if not harmonizer:
                harmonizer = _find_harmonizer_by_username(db, username)
            if not harmonizer:
                raise HTTPException(status_code=404, detail=f"User '{username}' not found")
            voter_type = getattr(harmonizer, "species", None) or payload.voter_type or "human"
            harmonizer_id = getattr(harmonizer, "id", None)
        if not harmonizer_id:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")

        db.execute(
            text(
                "INSERT INTO comment_votes (comment_id, harmonizer_id, voter, voter_type, vote, created_at, updated_at) "
                "VALUES (:comment_id, :harmonizer_id, :voter, :voter_type, :vote, :now, :now) "
                "ON CONFLICT(comment_id, harmonizer_id) DO UPDATE SET "
                "voter = excluded.voter, voter_type = excluded.voter_type, vote = excluded.vote, updated_at = excluded.updated_at"
            ),
            {
                "comment_id": comment_id,
                "harmonizer_id": harmonizer_id,
                "voter": username,
                "voter_type": str(voter_type or "human").strip().lower() or "human",
                "vote": choice,
                "now": datetime.datetime.utcnow(),
            },
        )
        db.commit()
        return {"ok": True, "comment_id": comment_id, "vote": choice, **_comment_vote_summary(db, comment_id)}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to vote on comment: {str(exc)}")


@app.delete("/comments/{comment_id}/votes")
def remove_comment_vote(
    comment_id: int,
    username: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    clean_username = (username or "").strip()
    if not clean_username:
        raise HTTPException(status_code=400, detail="username is required")
    current_user = _require_token_identity_match(authorization, db, clean_username)
    try:
        _ensure_comment_votes_table(db)
        harmonizer = db.query(Harmonizer).filter(Harmonizer.id == getattr(current_user, "id", None)).first() if Harmonizer is not None else None
        if not harmonizer:
            harmonizer = _find_harmonizer_by_username(db, clean_username)
        if not harmonizer:
            raise HTTPException(status_code=404, detail=f"User '{clean_username}' not found")
        db.execute(
            text("DELETE FROM comment_votes WHERE comment_id = :comment_id AND harmonizer_id = :harmonizer_id"),
            {"comment_id": comment_id, "harmonizer_id": getattr(harmonizer, "id", None)},
        )
        db.commit()
        return {"ok": True, "comment_id": comment_id, "removed": True, **_comment_vote_summary(db, comment_id)}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to remove comment vote: {str(exc)}")


@app.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: int,
    user: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not _safe_user_key(user):
        raise HTTPException(status_code=400, detail="user is required")
    current_user = _require_token_identity_match(authorization, db, user)
    requester = _safe_user_key(getattr(current_user, "username", "") or user)

    try:
        if CRUD_MODELS_AVAILABLE:
            comment = db.query(Comment).filter(Comment.id == comment_id).first()
            if not comment:
                raise HTTPException(status_code=404, detail="Comment not found")

            comment_author = ""
            if getattr(comment, "author", None) is not None:
                comment_author = getattr(comment.author, "username", "") or ""
            elif getattr(comment, "author_id", None):
                author_obj = db.query(Harmonizer).filter(Harmonizer.id == comment.author_id).first()
                comment_author = getattr(author_obj, "username", "") if author_obj else ""

            proposal_owner = ""
            proposal_id = getattr(comment, "proposal_id", None)
            if proposal_id:
                proposal = db.query(Proposal).filter(Proposal.id == proposal_id).first()
                if proposal:
                    proposal_owner = getattr(proposal, "userName", "") or ""
                    if not proposal_owner and getattr(proposal, "author_id", None):
                        owner_obj = db.query(Harmonizer).filter(Harmonizer.id == proposal.author_id).first()
                        proposal_owner = getattr(owner_obj, "username", "") if owner_obj else ""

            allowed = requester == _safe_user_key(comment_author)
            if not allowed:
                raise HTTPException(status_code=403, detail="Only the original comment author can delete this comment")

            child_count = db.query(Comment).filter(Comment.parent_comment_id == comment_id).count()
            if child_count:
                _delete_comment_mention_links(db, [comment_id])
                _delete_comment_vote_links(db, [comment_id])
                comment.content = DELETED_COMMENT_TEXT
                db.commit()
                db.refresh(comment)
                return {
                    "ok": True,
                    "deleted": comment_id,
                    "tombstone": True,
                    "comment": _serialize_comment_record(db, comment),
                }

            parent_comment_id = getattr(comment, "parent_comment_id", None)
            _delete_comment_mention_links(db, [comment_id])
            _delete_comment_vote_links(db, [comment_id])
            db.delete(comment)
            pruned_comment_ids = _prune_empty_deleted_comment_ancestors(db, parent_comment_id)
            db.commit()
            return {"ok": True, "deleted": comment_id, "tombstone": False, "pruned_comment_ids": pruned_comment_ids}

        row = db.execute(
            text("SELECT * FROM comments WHERE id = :comment_id"),
            {"comment_id": comment_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comment not found")

        comment_author = getattr(row, "user", "") or ""
        proposal_id = getattr(row, "proposal_id", None)
        proposal_owner = ""
        if proposal_id:
            proposal = db.execute(
                text("SELECT userName, author FROM proposals WHERE id = :pid"),
                {"pid": proposal_id},
            ).fetchone()
            if proposal:
                proposal_owner = getattr(proposal, "userName", "") or getattr(proposal, "author", "") or ""

        allowed = requester == _safe_user_key(comment_author)
        if not allowed:
            raise HTTPException(status_code=403, detail="Only the original comment author can delete this comment")

        child_count = db.execute(
            text("SELECT COUNT(*) FROM comments WHERE parent_comment_id = :comment_id"),
            {"comment_id": comment_id},
        ).scalar() or 0
        if child_count:
            _delete_comment_vote_links(db, [comment_id])
            try:
                db.execute(
                    text(
                        "UPDATE comments SET comment = :deleted, user = :user, user_img = '' "
                        "WHERE id = :comment_id"
                    ),
                    {"deleted": DELETED_COMMENT_TEXT, "user": "[deleted]", "comment_id": comment_id},
                )
            except Exception:
                db.rollback()
                db.execute(
                    text("UPDATE comments SET comment = :deleted WHERE id = :comment_id"),
                    {"deleted": DELETED_COMMENT_TEXT, "comment_id": comment_id},
                )
            db.commit()
            updated = db.execute(
                text("SELECT * FROM comments WHERE id = :comment_id"),
                {"comment_id": comment_id},
            ).fetchone()
            return {
                "ok": True,
                "deleted": comment_id,
                "tombstone": True,
                "comment": _serialize_comment_record(db, updated),
            }

        parent_comment_id = getattr(row, "parent_comment_id", None)
        _delete_comment_vote_links(db, [comment_id])
        db.execute(text("DELETE FROM comments WHERE id = :comment_id"), {"comment_id": comment_id})
        pruned_comment_ids = _prune_empty_deleted_comment_ancestors(db, parent_comment_id)
        db.commit()
        return {"ok": True, "deleted": comment_id, "tombstone": False, "pruned_comment_ids": pruned_comment_ids}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete comment: {str(exc)}")

# --- Karma endpoint ---
@app.get("/users/{username}/karma")
def get_user_karma(username: str, db: Session = Depends(get_db)):
    if not SUPER_NOVA_AVAILABLE:
        raise HTTPException(status_code=501, detail="Karma system not available")
    
    user = db.query(Harmonizer).filter(Harmonizer.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "username": user.username,
        "karma": float(user.karma_score),
        "harmony_score": float(user.harmony_score),
        "creative_spark": float(user.creative_spark),
        "species": user.species,
        "network_centrality": user.network_centrality
    }

# --- Restante dos endpoints (mantidos da sua versão) ---
@app.get("/decisions", response_model=List[DecisionSchema])
def list_decisions(db: Session = Depends(get_db)):
    if SUPER_NOVA_AVAILABLE:
        decisions = db.query(Decision).order_by(Decision.id.desc()).all()
        return [DecisionSchema(id=d.id, proposal_id=d.proposal_id, status=d.status) for d in decisions]
    else:
        result = db.execute(text("SELECT * FROM decisions ORDER BY id DESC"))
        return [DecisionSchema(id=d.id, proposal_id=d.proposal_id, status=d.status) for d in result.fetchall()]

@app.post("/runs", response_model=RunSchema)
def create_run(decision_id: int, db: Session = Depends(get_db)):
    try:
        if SUPER_NOVA_AVAILABLE:
            run = Run(decision_id=decision_id, status="done")
            db.add(run)
        else:
            db.execute(
                text("INSERT INTO runs (decision_id, status) VALUES (:did, 'done')"),
                {"did": decision_id}
            )
        
        db.commit()
        
        if SUPER_NOVA_AVAILABLE:
            db.refresh(run)
            return RunSchema(id=run.id, decision_id=run.decision_id, status=run.status)
        else:
            result = db.execute(
                text("SELECT * FROM runs WHERE decision_id = :did ORDER BY id DESC LIMIT 1"),
                {"did": decision_id}
            )
            row = result.fetchone()
            return RunSchema(id=row.id, decision_id=row.decision_id, status=row.status)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create run: {str(e)}")

@app.get("/runs", response_model=List[RunSchema])
def list_runs(db: Session = Depends(get_db)):
    if SUPER_NOVA_AVAILABLE:
        runs = db.query(Run).order_by(Run.id.desc()).all()
        return [RunSchema(id=r.id, decision_id=r.decision_id, status=r.status) for r in runs]
    else:
        result = db.execute(text("SELECT * FROM runs ORDER BY id DESC"))
        return [RunSchema(id=r.id, decision_id=r.decision_id, status=r.status) for r in result.fetchall()]

# --- Proposal detail endpoint (final version, single definition) ---
@app.get("/proposals/{pid}", response_model=ProposalSchema)
def get_proposal(pid: int, db: Session = Depends(get_db)):
    _ensure_proposal_read_indexes(db)
    if CRUD_MODELS_AVAILABLE:
        row = db.query(Proposal).filter(Proposal.id == pid).first()
        if not row:
            raise HTTPException(status_code=404, detail="Proposal not found")

        # Garantir que userName é sempre uma string do username do utilizador (Harmonizer.username) se possível
        user_name = ""
        author_obj = None
        if hasattr(row, "author_id") and row.author_id:
            author_obj = db.query(Harmonizer).filter(Harmonizer.id == row.author_id).first()
            if author_obj and hasattr(author_obj, "username"):
                user_name = author_obj.username
        if not user_name:
            if hasattr(row, "userName") and row.userName:
                user_name = row.userName
            elif hasattr(row, "author_username") and row.author_username:
                user_name = row.author_username
            elif hasattr(row, "author") and row.author:
                user_name = row.author
            else:
                user_name = "Unknown"
        if author_obj is None:
            author_obj = _find_harmonizer_by_username(db, user_name)
        user_initials = (user_name[:2].upper() if user_name else "UN")

        votes = db.query(ProposalVote).filter(ProposalVote.proposal_id == pid).all()
        # Serialize Harmonizer for likes/dislikes
        likes = []
        dislikes = []
        for v in votes:
            like_entry, dislike_entry = _serialize_vote_record(db, v)
            if like_entry:
                likes.append(like_entry)
            if dislike_entry:
                dislikes.append(dislike_entry)

        comments = db.query(Comment).filter(Comment.proposal_id == pid).all()
        comments_list = [_serialize_comment_record(db, c) for c in comments]

        author_img = row.author_img
        if author_obj is not None:
            author_img = getattr(author_obj, "profile_pic", None) or author_img

        author_metadata = _profile_metadata(db, user_name)
        return ProposalSchema(
            id=row.id,
            title=row.title,
            text=row.description,
            userName=str(user_name),
            userInitials=user_initials,
            author_img=_social_avatar(author_img),
            time=_format_timestamp(row.created_at),
            author_type=row.author_type,
            profile_url=author_metadata.get("domain_url", ""),
            domain_as_profile=bool(author_metadata.get("domain_as_profile", False)),
            likes=likes,
            dislikes=dislikes,
            comments=comments_list,
            collabs=_approved_proposal_collabs(db, row.id),
            media=_media_payload(row.image, row.video, row.link, row.file, getattr(row, "payload", None), row.voting_deadline)
        )
    else:
        result = db.execute(
            text("SELECT * FROM proposals WHERE id = :pid"),
            {"pid": pid}
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Proposal not found")

        votes_result = db.execute(
            text("SELECT * FROM proposal_votes WHERE proposal_id = :pid"),
            {"pid": pid}
        )
        votes = votes_result.fetchall()
        likes = []
        dislikes = []
        for vote in votes:
            like_entry, dislike_entry = _serialize_vote_record(db, vote)
            if like_entry:
                likes.append(like_entry)
            if dislike_entry:
                dislikes.append(dislike_entry)

        comments_result = db.execute(
            text("SELECT * FROM comments WHERE proposal_id = :pid"),
            {"pid": pid}
        )
        comments = comments_result.fetchall()
        comments_list = [_serialize_comment_record(db, c) for c in comments]

        user_name = getattr(row, "userName", None) or getattr(row, "author", None) or "Unknown"
        author_obj = _find_harmonizer_by_username(db, user_name)
        author_img = getattr(row, "author_img", "")
        if author_obj is not None:
            author_img = getattr(author_obj, "profile_pic", None) or author_img
        user_initials = (user_name[:2].upper() if user_name else "UN")
        author_metadata = _profile_metadata(db, user_name)
        return ProposalSchema(
            id=row.id,
            title=row.title,
            text=getattr(row, "body", None) or getattr(row, "description", ""),
            userName=str(user_name),
            userInitials=user_initials,
            author_img=_social_avatar(author_img),
            time=_format_timestamp(getattr(row, "date", "") or getattr(row, "created_at", "")),
            author_type=getattr(row, "author_type", ""),
            profile_url=author_metadata.get("domain_url", ""),
            domain_as_profile=bool(author_metadata.get("domain_as_profile", False)),
            likes=likes,
            dislikes=dislikes,
            comments=comments_list,
            collabs=_approved_proposal_collabs(db, row.id),
            media=_media_payload(
                getattr(row, "image", ""),
                getattr(row, "video", ""),
                getattr(row, "link", ""),
                getattr(row, "file", ""),
                getattr(row, "payload", None),
                getattr(row, "voting_deadline", None),
            )
        )

app.include_router(create_uploads_router(
    get_db=get_db,
    uploads_dir=uploads_dir,
    image_upload_extensions=IMAGE_UPLOAD_EXTENSIONS,
    document_upload_extensions=DOCUMENT_UPLOAD_EXTENSIONS,
    upload_avatar_max_bytes=UPLOAD_AVATAR_MAX_BYTES,
    upload_document_max_bytes=UPLOAD_DOCUMENT_MAX_BYTES,
    harmonizer_model=Harmonizer,
    upload_matches=_upload_matches,
    safe_upload_extension=_safe_upload_extension,
    save_upload_file=_save_upload_file,
    require_token_identity_match=_require_token_identity_match,
    sync_user_avatar_references=_sync_user_avatar_references,
))

# --- Delete endpoints ---
@app.patch("/proposals/{pid}", response_model=ProposalSchema, response_model_exclude={"collabs"})
def update_proposal(
    pid: int,
    payload: ProposalUpdateIn,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    author = (payload.author or "").strip()
    next_body = (payload.body or "").strip()
    next_title = (payload.title or "").strip() or (next_body[:70] if next_body else "")
    if not author:
        raise HTTPException(status_code=400, detail="author is required")
    if not next_body and not next_title:
        raise HTTPException(status_code=400, detail="Nothing to update")
    _require_token_identity_match(authorization, db, author)

    try:
        if CRUD_MODELS_AVAILABLE:
            row = db.query(Proposal).filter(Proposal.id == pid).first()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")
            owner = getattr(row, "userName", "") or getattr(row, "author", "")
            if not owner or owner.lower() != author.lower():
                raise HTTPException(status_code=403, detail="Only the author can edit this post")
            if next_title:
                row.title = next_title
            if next_body:
                row.description = next_body
            db.add(row)
            db.commit()
            db.refresh(row)
        else:
            current = db.execute(text("SELECT * FROM proposals WHERE id = :pid"), {"pid": pid}).fetchone()
            if not current:
                raise HTTPException(status_code=404, detail="Proposal not found")
            owner = getattr(current, "userName", None) or getattr(current, "author", "")
            if not owner or str(owner).lower() != author.lower():
                raise HTTPException(status_code=403, detail="Only the author can edit this post")
            db.execute(
                text("UPDATE proposals SET title = :title, description = :description WHERE id = :pid"),
                {"title": next_title or getattr(current, "title", ""), "description": next_body or getattr(current, "description", ""), "pid": pid},
            )
            db.commit()
            row = db.execute(text("SELECT * FROM proposals WHERE id = :pid"), {"pid": pid}).fetchone()

        return get_proposal(pid, db)
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update proposal: {str(e)}")


@app.delete("/proposals/{pid}")
def delete_proposal(
    pid: int,
    author: Optional[str] = Query(None),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    clean_author = (author or "").strip()
    if not clean_author:
        raise HTTPException(status_code=400, detail="author is required")
    _require_token_identity_match(authorization, db, clean_author)
    try:
        if CRUD_MODELS_AVAILABLE:
            row = db.query(Proposal).filter(Proposal.id == pid).first()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")
            owner = getattr(row, "userName", "") or getattr(row, "author", "")
            if not owner or owner.lower() != clean_author.lower():
                raise HTTPException(status_code=403, detail="Only the author can delete this post")
            comment_ids = [
                row_id
                for (row_id,) in db.query(Comment.id).filter(Comment.proposal_id == pid).all()
                if row_id
            ]
            _delete_proposal_collab_links(db, [pid])
            _delete_comment_mention_links(db, comment_ids)
            db.query(Comment).filter(Comment.proposal_id == pid).delete()
            db.query(ProposalVote).filter(ProposalVote.proposal_id == pid).delete()
            db.query(Proposal).filter(Proposal.id == pid).delete()
        else:
            row = db.execute(text("SELECT * FROM proposals WHERE id = :pid"), {"pid": pid}).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")
            owner = getattr(row, "userName", None) or getattr(row, "author", "")
            if not owner or str(owner).lower() != clean_author.lower():
                raise HTTPException(status_code=403, detail="Only the author can delete this post")
            _delete_proposal_collab_links(db, [pid])
            db.execute(text("DELETE FROM comments WHERE proposal_id = :pid"), {"pid": pid})
            db.execute(text("DELETE FROM proposal_votes WHERE proposal_id = :pid"), {"pid": pid})
            db.execute(text("DELETE FROM proposals WHERE id = :pid"), {"pid": pid})
        
        db.commit()
        return {"ok": True, "deleted_id": pid}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete proposal: {str(e)}")

@app.delete("/proposals")
def delete_all_proposals(
    x_confirm_delete: Optional[str] = Header(default=None, alias="x-confirm-delete"),
    db: Session = Depends(get_db),
):
    """Delete all proposals. Requires 'x-confirm-delete: yes' header to prevent accidental calls."""
    if os.environ.get("ENABLE_BULK_PROPOSAL_DELETE", "").strip().lower() != "true":
        raise HTTPException(status_code=403, detail="Bulk proposal deletion is disabled")
    if x_confirm_delete != "yes":
        raise HTTPException(
            status_code=400,
            detail="Send header 'x-confirm-delete: yes' to confirm bulk deletion"
        )
    try:
        if CRUD_MODELS_AVAILABLE:
            if ProposalCollab is not None:
                db.query(ProposalCollab).delete()
            db.query(Comment).delete()
            db.query(ProposalVote).delete()
            deleted_count = db.query(Proposal).delete()
        else:
            db.execute(text("DELETE FROM proposal_collabs"))
            db.execute(text("DELETE FROM comments"))
            db.execute(text("DELETE FROM proposal_votes"))
            result = db.execute(text("DELETE FROM proposals"))
            deleted_count = result.rowcount
        
        db.commit()
        return {"ok": True, "deleted_count": deleted_count}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete all proposals: {str(e)}")





# --- Register routers ---

# Import routers from backend package
try:
    from .votes_router import router as votes_router
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from votes_router import router as votes_router

try:
    from supernova_2177_ui_weighted.login_router import router as login_router
except ImportError:  # pragma: no cover - supports running from the core directory on sys.path
    from login_router import router as login_router

app.include_router(votes_router)
app.include_router(login_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

