from typing import Any, Callable, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session


def create_ai_readonly_router(
    *,
    get_db: Callable,
    connector_get_proposal_or_404: Callable,
    system_ai_actor_payload: Callable[[], Dict[str, Any]],
    generate_locked_ai_review: Callable,
    connector_action_proposal_model,
    connector_action_payload: Callable,
    proposal_vote_model,
    harmonizer_model,
    social_avatar: Callable,
    format_timestamp: Callable,
    public_ai_actor_payload: Callable,
    connector_proposal_title: Callable,
) -> APIRouter:
    router = APIRouter()

    @router.get("/proposals/{proposal_id}/system-ai-review", summary="Read the advisory SuperNova Protocol AI review")
    def get_system_ai_review(proposal_id: int, db: Session = Depends(get_db)):
        proposal = connector_get_proposal_or_404(db, proposal_id)
        actor = system_ai_actor_payload()
        review = generate_locked_ai_review(
            proposal=proposal,
            actor_payload=actor,
            allow_caution=True,
        )
        return {
            "mode": "public_read_only",
            "actor": actor,
            "review": {
                **review,
                "ai_actor_id": actor["id"],
                "ai_actor_type": actor["ai_actor_type"],
                "species": "ai",
                "approval_status": "published_advisory",
                "advisory": True,
            },
            "safety": {
                "read_only": True,
                "advisory_only": True,
                "no_vote_created": True,
                "no_comment_created": True,
                "no_automatic_execution": True,
            },
        }

    @router.get("/proposals/{proposal_id}/ai-review-ledger", summary="Read the public tri-species vote/review ledger")
    def get_ai_review_ledger(proposal_id: int, db: Session = Depends(get_db)):
        proposal = connector_get_proposal_or_404(db, proposal_id)
        system_review = get_system_ai_review(proposal_id, db)
        ai_review_results: Dict[str, Dict[str, Any]] = {}
        if connector_action_proposal_model is not None:
            actions = (
                db.query(connector_action_proposal_model)
                .filter(connector_action_proposal_model.action_type == "draft_ai_review")
                .filter(connector_action_proposal_model.status == "executed")
                .filter(connector_action_proposal_model.target_id == str(proposal_id))
                .all()
            )
            for action in actions:
                result_payload = connector_action_payload(getattr(action, "result_payload", None))
                actor_key = str(result_payload.get("actor") or "").lower()
                if actor_key:
                    ai_review_results[actor_key] = result_payload
                ai_actor_username = str(result_payload.get("ai_actor_username") or "").lower()
                if ai_actor_username:
                    ai_review_results[ai_actor_username] = result_payload

        groups: Dict[str, List[Dict[str, Any]]] = {
            "humans": [],
            "organizations": [],
            "personal_ai_delegates": [],
            "organization_ai_delegates": [],
            "system_ai": [system_review["review"]],
        }

        if proposal_vote_model is not None and harmonizer_model is not None:
            votes = db.query(proposal_vote_model).filter(proposal_vote_model.proposal_id == proposal_id).all()
            for vote in votes:
                voter = db.query(harmonizer_model).filter(
                    harmonizer_model.id == getattr(vote, "harmonizer_id", None)
                ).first()
                username = getattr(voter, "username", "") if voter else ""
                species = (getattr(voter, "species", None) or getattr(vote, "voter_type", None) or "human").lower()
                row = {
                    "username": username,
                    "species": species,
                    "avatar_url": social_avatar(getattr(voter, "profile_pic", "")) if voter else "",
                    "vote": getattr(vote, "vote", None) or getattr(vote, "choice", None),
                    "timestamp": format_timestamp(getattr(vote, "created_at", None)),
                }
                if species == "company":
                    row["actor_type_badge"] = "Organization"
                    groups["organizations"].append(row)
                elif species == "ai":
                    review_payload = ai_review_results.get(str(username or "").lower()) or {}
                    actor_profile = public_ai_actor_payload(db, username) or {}
                    row["actor_type_badge"] = "AI delegate"
                    row["ai_actor_type"] = (
                        review_payload.get("ai_actor_type")
                        or actor_profile.get("ai_actor_type")
                        or "principal_delegate"
                    )
                    row["custody_label"] = (
                        review_payload.get("custody_label")
                        or actor_profile.get("custody_label")
                        or (f"AI delegate account @{username}" if username else "AI delegate account")
                    )
                    row["reasoning_summary"] = (
                        review_payload.get("reasoning_summary")
                        or "AI reasoning is required for official AI reviews."
                    )
                    row["reasoning_hash"] = review_payload.get("reasoning_hash")
                    row["model_identity"] = review_payload.get("model_identity") or actor_profile.get("model_identity")
                    row["prompt_policy_version"] = (
                        review_payload.get("prompt_policy_version")
                        or actor_profile.get("prompt_policy_version")
                    )
                    row["ai_actor_profile_url"] = f"/ai/{username}" if username else ""
                    groups["personal_ai_delegates"].append(row)
                else:
                    row["actor_type_badge"] = "Human"
                    groups["humans"].append(row)

        return {
            "mode": "public_read_only",
            "proposal_id": getattr(proposal, "id", proposal_id),
            "proposal_title": connector_proposal_title(proposal),
            "groups": groups,
            "safety": {
                "read_only": True,
                "system_ai_advisory_only": True,
                "no_automatic_execution": True,
                "mcp_write_tools_enabled": False,
            },
        }

    return router
