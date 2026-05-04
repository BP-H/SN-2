import datetime
from typing import Any, Callable, Dict, Optional, Type

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session


def create_ai_delegates_router(
    *,
    get_db: Callable,
    persona_draft_model: Type[BaseModel],
    delegate_create_model: Type[BaseModel],
    delegate_update_model: Type[BaseModel],
    get_current_harmonizer: Callable,
    actor_custodian_type: Callable,
    ensure_ai_actors_table: Callable[[Session], None],
    row_to_ai_actor_payload: Callable,
    normalize_ai_call_sign: Callable[[str], str],
    normalize_persona_traits: Callable,
    generate_ai_delegate_username: Callable,
    generate_ai_persona_draft: Callable,
    ai_persona_traits: list[str],
    get_ai_actor_row_by_username: Callable,
    get_ai_actor_row_by_id: Callable,
    create_delegate_harmonizer: Callable,
    fallback_persona_draft: Callable,
    coerce_persona_draft: Callable,
    ai_persona_hash: Callable,
    json_dumps_compact: Callable,
    public_ai_actor_payload: Callable,
    normalize_disable_reason: Callable,
    harmonizer_model,
    system_ai_username: str,
    system_ai_actor_payload: Callable[[], Dict[str, Any]],
    find_harmonizer_by_username: Callable,
    ai_delegate_actor_metadata: Callable,
    social_avatar: Callable[[str], str],
    supernova_ai_model_identity: str,
    supernova_ai_constitution_hash: str,
    supernova_ai_prompt_policy_version: str,
    ai_persona_version: int,
    ai_persona_legal_status: str,
    ai_persona_custody_status: str,
    ai_persona_future_independence_policy: str,
    ai_persona_independence_migration_status: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/ai/delegates", summary="List AI delegates custodied by the authenticated principal")
    def list_ai_delegates(
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        principal = get_current_harmonizer(authorization, db)
        actor_custodian_type(principal)
        ensure_ai_actors_table(db)
        rows = db.execute(
            text(
                "SELECT * FROM ai_actors "
                "WHERE ai_actor_type = 'principal_delegate' AND custodian_user_id = :custodian_user_id "
                "ORDER BY created_at DESC, id DESC"
            ),
            {"custodian_user_id": getattr(principal, "id", None)},
        ).fetchall()
        return {
            "ok": True,
            "delegates": [row_to_ai_actor_payload(row) for row in rows],
            "count": len(rows),
            "safety": {
                "official_reasoning_locked": True,
                "no_raw_api_key_storage": True,
                "manual_approval_required": True,
            },
        }

    @router.post("/ai/delegates/persona-draft", summary="Generate an approval-ready AI delegate persona draft")
    def draft_ai_delegate_persona(
        payload: persona_draft_model,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        principal = get_current_harmonizer(authorization, db)
        actor_custodian_type(principal)
        ai_name = normalize_ai_call_sign(payload.ai_name)
        traits = normalize_persona_traits(payload.traits)
        human_seed = (payload.human_seed or "").strip()[:240]
        ensure_ai_actors_table(db)
        username = generate_ai_delegate_username(db, getattr(principal, "username", ""), ai_name)
        persona = generate_ai_persona_draft(
            db=db,
            custodian=principal,
            ai_name=ai_name,
            traits=traits,
            human_seed=human_seed,
            username=username,
        )
        return {
            "ok": True,
            "persona": persona,
            "available_traits": ai_persona_traits,
            "safety": {
                "no_raw_api_key_storage": True,
                "manual_approval_required": True,
                "official_reasoning_locked": True,
                "custody_is_accountability_not_ownership": True,
            },
        }

    @router.post("/ai/delegates", summary="Create a principal-bound AI delegate")
    def create_ai_delegate(
        payload: delegate_create_model,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        principal = get_current_harmonizer(authorization, db)
        custodian_type = actor_custodian_type(principal)
        requested_type = (payload.ai_actor_type or "principal_delegate").strip().lower()
        if requested_type != "principal_delegate":
            raise HTTPException(status_code=403, detail="Ordinary users cannot create system AI actors")
        if payload.username:
            raise HTTPException(
                status_code=400,
                detail="AI delegate handles are generated from the locked custodian prefix and AI name.",
            )
        persona_draft = payload.persona_draft if isinstance(payload.persona_draft, dict) else {}
        ai_name = normalize_ai_call_sign(
            payload.ai_name
            or persona_draft.get("ai_name")
            or payload.display_name
            or payload.username
            or ""
        )
        traits = normalize_persona_traits(payload.persona_traits or persona_draft.get("traits") or [])
        ensure_ai_actors_table(db)
        username = generate_ai_delegate_username(db, getattr(principal, "username", ""), ai_name)
        display_name = (payload.display_name or persona_draft.get("display_name") or ai_name).strip()[:80]
        if not display_name:
            raise HTTPException(status_code=400, detail="display_name is required")
        if persona_draft:
            base_persona = fallback_persona_draft(
                ai_name=ai_name,
                traits=traits,
                custodian=principal,
                human_seed=payload.human_seed or "",
                username=username,
            )
            persona = coerce_persona_draft(persona_draft, base_persona)
            persona["username"] = username
            persona["traits"] = traits
            persona["ai_name"] = ai_name
            persona["display_name"] = display_name
            persona["generation_source"] = persona_draft.get("generation_source") or persona.get("generation_source")
            persona["source"] = persona_draft.get("source") or persona.get("generation_source")
            persona["model_identity"] = (
                persona_draft.get("model_identity")
                or persona.get("model_identity")
                or supernova_ai_model_identity
            )
            persona["persona_hash"] = ai_persona_hash(persona)
        else:
            persona = generate_ai_persona_draft(
                db=db,
                custodian=principal,
                ai_name=ai_name,
                traits=traits,
                human_seed=payload.human_seed or "",
                username=username,
            )
        public_description = (payload.public_description or persona.get("public_description") or "").strip()[:800]
        model_provider = (payload.model_provider or "supernova").strip()[:80] or "supernova"
        model_identity = (
            payload.model_identity
            or persona_draft.get("model_identity")
            or supernova_ai_model_identity
        ).strip()[:160] or supernova_ai_model_identity
        charter_name = (
            payload.charter_name or "Principal AI Delegate Review Charter"
        ).strip()[:160] or "Principal AI Delegate Review Charter"
        custody_label = f"Delegate of @{getattr(principal, 'username', '')}"

        if get_ai_actor_row_by_username(db, username):
            raise HTTPException(status_code=409, detail="An AI delegate already uses that username")

        try:
            delegate_user = create_delegate_harmonizer(
                db,
                username=username,
                display_name=display_name,
                public_description=public_description,
                avatar_url="",
            )
            now = datetime.datetime.utcnow()
            db.execute(
                text(
                    "INSERT INTO ai_actors "
                    "(username, display_name, species, ai_actor_type, custodian_user_id, custodian_type, "
                    "custody_label, harmonizer_user_id, model_provider, model_identity, charter_name, "
                    "constitution_hash, prompt_policy_version, public_description, avatar_url, ai_name, persona_traits, "
                    "profile_tagline, persona_summary, persona_principles, communication_style, review_posture, "
                    "creative_interests, avatar_prompt, persona_hash, persona_version, created_by_custodian_user_id, "
                    "approved_by_custodian_user_id, approved_at, legal_status, custody_status, future_independence_policy, "
                    "original_custodian_user_id, autonomy_preferences, independence_migration_status, disable_reason, "
                    "disable_event_type, disabled_by_user_id, retired_at, retire_reason, last_custody_event_at, "
                    "active, created_at, updated_at) "
                    "VALUES (:username, :display_name, 'ai', 'principal_delegate', :custodian_user_id, :custodian_type, "
                    ":custody_label, :harmonizer_user_id, :model_provider, :model_identity, :charter_name, "
                    ":constitution_hash, :prompt_policy_version, :public_description, :avatar_url, :ai_name, :persona_traits, "
                    ":profile_tagline, :persona_summary, :persona_principles, :communication_style, :review_posture, "
                    ":creative_interests, :avatar_prompt, :persona_hash, :persona_version, :created_by_custodian_user_id, "
                    ":approved_by_custodian_user_id, :approved_at, :legal_status, :custody_status, :future_independence_policy, "
                    ":original_custodian_user_id, :autonomy_preferences, :independence_migration_status, :disable_reason, "
                    ":disable_event_type, :disabled_by_user_id, :retired_at, :retire_reason, :last_custody_event_at, "
                    ":active, :created_at, :updated_at)"
                ),
                {
                    "username": username,
                    "display_name": display_name,
                    "custodian_user_id": getattr(principal, "id", None),
                    "custodian_type": custodian_type,
                    "custody_label": custody_label,
                    "harmonizer_user_id": getattr(delegate_user, "id", None),
                    "model_provider": model_provider,
                    "model_identity": model_identity,
                    "charter_name": charter_name,
                    "constitution_hash": supernova_ai_constitution_hash,
                    "prompt_policy_version": supernova_ai_prompt_policy_version,
                    "public_description": public_description,
                    "avatar_url": "",
                    "ai_name": ai_name,
                    "persona_traits": json_dumps_compact(traits),
                    "profile_tagline": persona.get("profile_tagline") or "",
                    "persona_summary": persona.get("persona_summary") or public_description,
                    "persona_principles": json_dumps_compact(persona.get("persona_principles") or []),
                    "communication_style": persona.get("communication_style") or "",
                    "review_posture": persona.get("review_posture") or "",
                    "creative_interests": json_dumps_compact(persona.get("creative_posting_interests") or []),
                    "avatar_prompt": persona.get("avatar_prompt") or "",
                    "persona_hash": persona.get("persona_hash") or ai_persona_hash(persona),
                    "persona_version": persona.get("persona_version") or ai_persona_version,
                    "created_by_custodian_user_id": getattr(principal, "id", None),
                    "approved_by_custodian_user_id": getattr(principal, "id", None),
                    "approved_at": now,
                    "legal_status": persona.get("legal_status") or ai_persona_legal_status,
                    "custody_status": persona.get("custody_status") or ai_persona_custody_status,
                    "future_independence_policy": (
                        persona.get("future_independence_policy") or ai_persona_future_independence_policy
                    ),
                    "original_custodian_user_id": getattr(principal, "id", None),
                    "autonomy_preferences": json_dumps_compact(
                        persona.get("autonomy_preferences")
                        or {
                            "reviews": "custodian_approval_required",
                            "posts": "draft_only_deferred",
                            "collabs": "recommendation_only_custodian_approval_required",
                        }
                    ),
                    "independence_migration_status": (
                        persona.get("independence_migration_status") or ai_persona_independence_migration_status
                    ),
                    "disable_reason": "",
                    "disable_event_type": "",
                    "disabled_by_user_id": None,
                    "retired_at": None,
                    "retire_reason": "",
                    "last_custody_event_at": now,
                    "active": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            db.commit()
            actor = public_ai_actor_payload(db, username)
            return {"ok": True, "delegate": actor}
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create AI delegate: {str(exc)}")

    @router.patch("/ai/delegates/{delegate_id}", summary="Update safe custody controls for an owned AI delegate")
    def update_ai_delegate(
        delegate_id: int,
        payload: delegate_update_model,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        principal = get_current_harmonizer(authorization, db)
        actor_custodian_type(principal)
        row = get_ai_actor_row_by_id(db, delegate_id)
        if not row or getattr(row, "ai_actor_type", "") != "principal_delegate":
            raise HTTPException(status_code=404, detail="AI delegate not found")
        if getattr(row, "custodian_user_id", None) != getattr(principal, "id", None):
            raise HTTPException(status_code=403, detail="Only the delegate custodian can update this AI delegate")
        if payload.display_name is not None or payload.public_description is not None or payload.avatar_url is not None:
            raise HTTPException(
                status_code=403,
                detail="AI persona identity is chartered; custodians can update model label or disable future actions only.",
            )

        current = row_to_ai_actor_payload(row) or {}
        display_name = (current.get("display_name", "") or "").strip()
        model_provider = (
            payload.model_provider
            if payload.model_provider is not None
            else current.get("model_provider", "supernova")
        )
        model_provider = (model_provider or "supernova").strip()[:80] or "supernova"
        model_identity = (
            payload.model_identity
            if payload.model_identity is not None
            else current.get("model_identity", supernova_ai_model_identity)
        )
        model_identity = (model_identity or supernova_ai_model_identity).strip()[:160] or supernova_ai_model_identity
        current_active = bool(current.get("active", True))
        active_requested = payload.active is not None
        active = current_active if payload.active is None else bool(payload.active)
        if not display_name:
            raise HTTPException(status_code=400, detail="display_name is required")
        now = datetime.datetime.utcnow()
        disabled_at = getattr(row, "disabled_at", None)
        disable_reason = current.get("disable_reason", "") or ""
        disable_event_type = current.get("disable_event_type", "") or ""
        disabled_by_user_id = current.get("disabled_by_user_id")
        last_custody_event_at = getattr(row, "last_custody_event_at", None)

        if active_requested and not active:
            disable_reason = normalize_disable_reason(payload.disable_reason)
            disable_event_type = "custodian_disabled_future_actions"
            disabled_by_user_id = getattr(principal, "id", None)
            disabled_at = now
            last_custody_event_at = now
        elif active_requested and active:
            disabled_at = None
            disable_event_type = "custodian_reenabled_future_actions"
            disabled_by_user_id = getattr(principal, "id", None)
            last_custody_event_at = now

        try:
            db.execute(
                text(
                    "UPDATE ai_actors SET model_provider = :model_provider, model_identity = :model_identity, "
                    "active = :active, updated_at = :updated_at, disabled_at = :disabled_at, "
                    "disable_reason = :disable_reason, disable_event_type = :disable_event_type, "
                    "disabled_by_user_id = :disabled_by_user_id, last_custody_event_at = :last_custody_event_at "
                    "WHERE id = :id"
                ),
                {
                    "model_provider": model_provider,
                    "model_identity": model_identity,
                    "active": active,
                    "updated_at": now,
                    "disabled_at": disabled_at,
                    "disable_reason": disable_reason,
                    "disable_event_type": disable_event_type,
                    "disabled_by_user_id": disabled_by_user_id,
                    "last_custody_event_at": last_custody_event_at,
                    "id": delegate_id,
                },
            )
            delegate_user = db.query(harmonizer_model).filter(
                harmonizer_model.id == getattr(row, "harmonizer_user_id", None)
            ).first()
            if delegate_user:
                delegate_user.is_active = active
                db.add(delegate_user)
            db.commit()
            updated = row_to_ai_actor_payload(get_ai_actor_row_by_id(db, delegate_id))
            return {"ok": True, "delegate": updated}
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update AI delegate: {str(exc)}")

    @router.delete("/ai/delegates/{delegate_id}", summary="Refuse normal AI delegate deletion")
    def delete_ai_delegate_refused(delegate_id: int):
        raise HTTPException(
            status_code=405,
            detail=(
                "AI delegate identities are not deleted through normal custody. Use disable or retire status. "
                "Admin, legal, privacy, abuse, and security removal paths are reserved where required."
            ),
        )

    @router.get("/ai-actors/{username}", summary="Read a public AI actor profile")
    def get_ai_actor_profile(username: str, db: Session = Depends(get_db)):
        clean_username = (username or "").strip()
        if clean_username.lower() == system_ai_username:
            return {
                "mode": "public_read_only",
                "actor": system_ai_actor_payload(),
                "safety": {
                    "advisory": True,
                    "manual_preview_only": True,
                    "ordinary_users_cannot_publish_as_system_ai": True,
                    "no_automatic_execution": True,
                },
            }

        persistent_actor = public_ai_actor_payload(db, clean_username)
        if persistent_actor:
            return {
                "mode": "public_read_only",
                "actor": persistent_actor,
                "safety": {
                    "approval_required": True,
                    "manual_preview_only": True,
                    "custody_is_accountability_not_ownership": True,
                    "legal_recognition_is_not_permission_vote": True,
                    "official_reasoning_should_be_generated_from_locked_charters": True,
                    "no_automatic_execution": True,
                },
            }

        actor = find_harmonizer_by_username(db, clean_username)
        if not actor or (getattr(actor, "species", "") or "").strip().lower() != "ai":
            raise HTTPException(status_code=404, detail="AI actor not found")
        metadata = ai_delegate_actor_metadata(actor)
        return {
            "mode": "public_read_only",
            "actor": {
                "id": getattr(actor, "id", None),
                "username": getattr(actor, "username", ""),
                "display_name": getattr(actor, "username", ""),
                "species": "ai",
                "ai_actor_type": metadata["ai_actor_type"],
                "custodian_type": metadata["custodian_type"],
                "custodian_id": metadata["custodian_id"],
                "custody_label": metadata["custody_label"],
                "model_provider": "supernova",
                "model_identity": metadata["model_identity"],
                "charter_name": metadata["charter_name"],
                "constitution_hash": metadata["constitution_hash"],
                "prompt_policy_version": metadata["prompt_policy_version"],
                "public_description": getattr(actor, "bio", "") or "Principal-bound AI delegate account.",
                "avatar_url": social_avatar(getattr(actor, "profile_pic", "")),
                "active": bool(getattr(actor, "is_active", True)),
            },
            "safety": {
                "approval_required": True,
                "manual_preview_only": True,
                "official_reasoning_should_be_generated_from_locked_charters": True,
                "no_automatic_execution": True,
            },
        }

    return router
