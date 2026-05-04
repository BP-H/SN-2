import datetime
from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from .supernova_runtime import runtime_status
except ImportError:  # pragma: no cover - supports running backend/app.py directly
    from supernova_runtime import runtime_status


def build_supernova_runtime_payload(
    runtime: Dict[str, Any],
    supernova_available: bool,
    include_routes: bool = True,
) -> Dict[str, Any]:
    payload = runtime_status(runtime)
    payload["integration"] = "connected" if supernova_available else "disconnected"
    payload["mount_path"] = "/core" if payload.get("core_mounted") else None
    payload["wrapper_routes_stable"] = True
    if not include_routes:
        routes = payload.get("core_routes") or []
        payload["core_routes_sample"] = routes[:8]
        payload.pop("core_routes", None)
    return payload


def build_cors_diagnostics(cors_config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "cors_mode": cors_config["mode"],
        "open_federation_mode": cors_config["public_api_cors_open"],
        "cors_credentials": False,
        "allowed_origins_count": len(cors_config["origins"]),
        "cors_warning": cors_config["warning"],
        "cors_note": cors_config["note"],
        "identity_model": "open public reads with token-checked writes; no cross-origin cookies",
    }


def create_status_router(
    *,
    get_db: Callable,
    db_engine_url: str,
    cors_config: Dict[str, Any],
    runtime: Dict[str, Any],
    supernova_available: bool,
    supernova_core_routes: list,
    status_payload_builder: Callable[[Session], Dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/health", summary="Check API health")
    def health(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception:
            db_status = "disconnected"

        supernova_runtime = build_supernova_runtime_payload(
            runtime,
            supernova_available,
            include_routes=False,
        )
        return {
            "ok": True,
            "database": db_status,
            "database_engine": db_engine_url,
            **build_cors_diagnostics(cors_config),
            "supernova_integration": supernova_runtime["integration"],
            "supernova": supernova_runtime,
            "timestamp": datetime.datetime.now().isoformat(),
        }

    @router.get("/supernova-status", summary="Check SuperNova integration status")
    def supernova_status():
        supernova_runtime = build_supernova_runtime_payload(
            runtime,
            supernova_available,
            include_routes=True,
        )
        return {
            "supernova_connected": supernova_available,
            "supernova": supernova_runtime,
            "database_engine": db_engine_url,
            **build_cors_diagnostics(cors_config),
            "features_available": {
                "weighted_voting": supernova_available,
                "karma_system": supernova_available,
                "governance": supernova_available,
                "core_routes": bool(supernova_core_routes),
                "search_filters": True,
                "advanced_sorting": True,
            },
        }

    @router.get("/status", tags=["System"])
    def get_status(db: Session = Depends(get_db)):
        return status_payload_builder(db)

    return router
