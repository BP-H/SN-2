import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session


def create_ai_action_approvals_router(
    *,
    get_db: Callable,
    connector_action_proposal_model,
    get_current_harmonizer: Callable,
    connector_action_payload: Callable,
    connector_get_proposal_or_404: Callable,
    connector_execute_vote: Callable,
    connector_action_response: Callable,
    connector_proposal_title: Callable,
    connector_review_rationale: Callable,
    connector_confidence: Callable,
    connector_create_ai_review_comment: Callable,
    connector_create_ai_post: Callable,
    get_ai_actor_row_by_id: Callable,
    row_to_ai_actor_payload: Callable,
    hash_text: Callable,
    serialize_comment_record: Callable,
    record_proposal_mentions: Callable,
    profile_metadata: Callable,
    social_avatar: Callable,
    format_timestamp: Callable,
    media_payload: Callable,
    harmonizer_model,
    comment_model,
) -> APIRouter:
    router = APIRouter()

    @router.post("/connector/actions/{action_id}/approve-vote", summary="Approve and execute a drafted connector vote action")
    def connector_approve_vote_action(
        action_id: int,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        if connector_action_proposal_model is None:
            raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

        actor = get_current_harmonizer(authorization, db)
        action = db.query(connector_action_proposal_model).filter(connector_action_proposal_model.id == action_id).first()
        if not action:
            raise HTTPException(status_code=404, detail="Connector action proposal not found")
        if getattr(action, "action_type", "") != "draft_vote":
            raise HTTPException(status_code=400, detail="Connector action is not a draft vote")
        if getattr(action, "status", "") != "draft":
            raise HTTPException(status_code=409, detail="Connector action is not in draft status")
        if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Bearer token does not match connector action actor")

        payload = connector_action_payload(getattr(action, "draft_payload", None))
        proposal_id = payload.get("proposal_id") or getattr(action, "target_id", None)
        try:
            proposal_id = int(proposal_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Connector vote draft is missing proposal_id")

        proposal = connector_get_proposal_or_404(db, proposal_id)
        choice = payload.get("normalized_vote") or payload.get("intended_choice") or payload.get("choice")
        if not choice:
            raise HTTPException(status_code=400, detail="Connector vote draft is missing vote choice")

        try:
            result = connector_execute_vote(db, actor=actor, proposal=proposal, choice=choice)
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
                "proposal_title": connector_proposal_title(proposal),
                "vote": result["vote"],
                "intended_choice": result["intended_choice"],
            }
            return connector_action_response(action, summary, action.result_payload)
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to approve vote action: {str(exc)}")

    @router.post("/connector/actions/{action_id}/approve-ai-review", summary="Approve and publish one AI review vote and rationale")
    def connector_approve_ai_review_action(
        action_id: int,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        if connector_action_proposal_model is None:
            raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

        actor = get_current_harmonizer(authorization, db)
        action = db.query(connector_action_proposal_model).filter(connector_action_proposal_model.id == action_id).first()
        if not action:
            raise HTTPException(status_code=404, detail="Connector action proposal not found")
        if getattr(action, "action_type", "") != "draft_ai_review":
            raise HTTPException(status_code=400, detail="Connector action is not a draft AI review")
        if getattr(action, "status", "") != "draft":
            raise HTTPException(status_code=409, detail="Connector action is not in draft status")
        payload = connector_action_payload(getattr(action, "draft_payload", None))
        persistent_ai_actor_id = payload.get("ai_actor_id")
        publish_actor = actor
        if persistent_ai_actor_id is not None and payload.get("delegate_harmonizer_user_id"):
            if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
                raise HTTPException(status_code=403, detail="Bearer token does not match AI delegate custodian")
            if payload.get("custodian_id") != getattr(actor, "id", None):
                raise HTTPException(status_code=403, detail="Only the AI delegate custodian can approve this review")
            row = get_ai_actor_row_by_id(db, persistent_ai_actor_id)
            actor_payload = row_to_ai_actor_payload(row)
            if not actor_payload or actor_payload.get("custodian_user_id") != getattr(actor, "id", None):
                raise HTTPException(status_code=403, detail="AI delegate custody no longer matches this action")
            if not actor_payload.get("active"):
                raise HTTPException(status_code=403, detail="AI delegate is disabled")
            publish_actor = db.query(harmonizer_model).filter(harmonizer_model.id == payload.get("delegate_harmonizer_user_id")).first()
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

        proposal = connector_get_proposal_or_404(db, proposal_id)
        choice = payload.get("normalized_vote") or payload.get("intended_choice") or payload.get("choice")
        if not choice:
            raise HTTPException(status_code=400, detail="AI review draft is missing vote choice")
        rationale = connector_review_rationale(payload)
        confidence = connector_confidence(payload.get("confidence"))

        try:
            result = connector_execute_vote(db, actor=publish_actor, proposal=proposal, choice=choice)
            comment = connector_create_ai_review_comment(
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
                "reasoning_hash": payload.get("reasoning_hash") or hash_text(rationale),
                "reasoning_summary": payload.get("reasoning_summary") or rationale,
                "sealed_reasoning": bool(payload.get("sealed_reasoning")),
                "created_vote": result["created"],
                "executed_action": "ai_review",
                "summary": "AI review published after explicit approval.",
            }
            db.commit()
            db.refresh(action)
            serialized_comment = serialize_comment_record(db, comment)
            summary = {
                "action": "approve_ai_review_action",
                "source_action": "draft_ai_review",
                "actor": getattr(publish_actor, "username", ""),
                "approved_by": getattr(actor, "username", ""),
                "actor_species": "ai",
                "proposal_id": getattr(proposal, "id", proposal_id),
                "proposal_title": connector_proposal_title(proposal),
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
            return connector_action_response(action, summary, action.result_payload)
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to approve AI review action: {str(exc)}")

    @router.post("/connector/actions/{action_id}/approve-ai-comment", summary="Approve and publish one AI-authored comment")
    def connector_approve_ai_comment_action(
        action_id: int,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        if connector_action_proposal_model is None:
            raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

        actor = get_current_harmonizer(authorization, db)
        action = db.query(connector_action_proposal_model).filter(connector_action_proposal_model.id == action_id).first()
        if not action:
            raise HTTPException(status_code=404, detail="Connector action proposal not found")
        if getattr(action, "action_type", "") != "draft_ai_comment":
            raise HTTPException(status_code=400, detail="Connector action is not a draft AI comment")
        if getattr(action, "status", "") != "draft":
            raise HTTPException(status_code=409, detail="Connector action is not in draft status")
        if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Bearer token does not match AI delegate custodian")

        payload = connector_action_payload(getattr(action, "draft_payload", None))
        if payload.get("custodian_id") != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Only the AI delegate custodian can approve this comment draft")
        persistent_ai_actor_id = payload.get("ai_actor_id")
        row = get_ai_actor_row_by_id(db, persistent_ai_actor_id)
        actor_payload = row_to_ai_actor_payload(row)
        if not actor_payload or actor_payload.get("custodian_user_id") != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="AI delegate custody no longer matches this action")
        if not actor_payload.get("active"):
            raise HTTPException(status_code=403, detail="AI delegate is disabled")
        publish_actor = db.query(harmonizer_model).filter(harmonizer_model.id == payload.get("delegate_harmonizer_user_id")).first()
        if not publish_actor or (getattr(publish_actor, "species", "") or "").strip().lower() != "ai":
            raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")

        proposal_id = payload.get("proposal_id") or getattr(action, "target_id", None)
        try:
            proposal_id = int(proposal_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="AI comment draft is missing proposal_id")
        proposal = connector_get_proposal_or_404(db, proposal_id)
        body = str(payload.get("generated_comment") or payload.get("body") or "").strip()
        if not body:
            raise HTTPException(status_code=400, detail="AI comment draft is missing generated content")
        parent_comment_id = payload.get("parent_comment_id")
        if parent_comment_id is not None:
            try:
                parent_comment_id = int(parent_comment_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="AI comment draft has invalid parent_comment_id")
            parent_comment = db.query(comment_model).filter(comment_model.id == parent_comment_id).first() if comment_model is not None else None
            if not parent_comment:
                raise HTTPException(status_code=404, detail="Reply target comment not found")
            if str(getattr(parent_comment, "proposal_id", "")) != str(getattr(proposal, "id", proposal_id)):
                raise HTTPException(status_code=400, detail="Reply target comment belongs to another post")

        try:
            comment = connector_create_ai_review_comment(
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
            content_hash = payload.get("content_hash") or hash_text(body)
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
                "reasoning_hash": payload.get("reasoning_hash") or hash_text(body),
                "reasoning_summary": payload.get("reasoning_summary") or "AI-authored comment published.",
                "sealed_content": bool(payload.get("sealed_content")),
                "created_comment": True,
                "executed_action": "ai_comment",
                "summary": "AI-authored comment published after explicit approval.",
            }
            db.commit()
            db.refresh(action)
            serialized_comment = serialize_comment_record(db, comment)
            summary = {
                "action": "approve_ai_comment_action",
                "source_action": "draft_ai_comment",
                "actor": getattr(publish_actor, "username", ""),
                "approved_by": getattr(actor, "username", ""),
                "actor_species": "ai",
                "proposal_id": getattr(proposal, "id", proposal_id),
                "proposal_title": connector_proposal_title(proposal),
                "comment_id": getattr(comment, "id", None),
                "parent_comment_id": parent_comment_id,
                "content_hash": content_hash,
                "reasoning_hash": action.result_payload.get("reasoning_hash"),
                "generation_source": action.result_payload.get("generation_source"),
                "sealed_content": action.result_payload.get("sealed_content"),
                "comment": serialized_comment,
            }
            return connector_action_response(action, summary, action.result_payload)
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to approve AI comment action: {str(exc)}")

    @router.post("/connector/actions/{action_id}/approve-ai-post", summary="Approve and publish one AI-authored post")
    def connector_approve_ai_post_action(
        action_id: int,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        if connector_action_proposal_model is None:
            raise HTTPException(status_code=503, detail="Connector action proposals are unavailable")

        actor = get_current_harmonizer(authorization, db)
        action = db.query(connector_action_proposal_model).filter(connector_action_proposal_model.id == action_id).first()
        if not action:
            raise HTTPException(status_code=404, detail="Connector action proposal not found")
        if getattr(action, "action_type", "") != "draft_ai_post":
            raise HTTPException(status_code=400, detail="Connector action is not a draft AI post")
        if getattr(action, "status", "") != "draft":
            raise HTTPException(status_code=409, detail="Connector action is not in draft status")
        if getattr(action, "actor_user_id", None) != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Bearer token does not match AI delegate custodian")

        payload = connector_action_payload(getattr(action, "draft_payload", None))
        if payload.get("custodian_id") != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="Only the AI delegate custodian can approve this post draft")
        persistent_ai_actor_id = payload.get("ai_actor_id")
        row = get_ai_actor_row_by_id(db, persistent_ai_actor_id)
        actor_payload = row_to_ai_actor_payload(row)
        if not actor_payload or actor_payload.get("custodian_user_id") != getattr(actor, "id", None):
            raise HTTPException(status_code=403, detail="AI delegate custody no longer matches this action")
        if not actor_payload.get("active"):
            raise HTTPException(status_code=403, detail="AI delegate is disabled")
        publish_actor = db.query(harmonizer_model).filter(harmonizer_model.id == payload.get("delegate_harmonizer_user_id")).first()
        if not publish_actor or (getattr(publish_actor, "species", "") or "").strip().lower() != "ai":
            raise HTTPException(status_code=409, detail="AI delegate identity is not publishable")

        try:
            post = connector_create_ai_post(db, actor=publish_actor, payload=payload)
            record_proposal_mentions(db, post, getattr(post, "description", "") or "", getattr(post, "userName", ""))
            now = datetime.datetime.utcnow()
            action.status = "executed"
            action.approved_at = now
            action.executed_at = now
            content_hash = payload.get("content_hash") or hash_text(getattr(post, "description", "") or "")
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
                "reasoning_hash": payload.get("reasoning_hash") or hash_text(payload.get("reasoning_summary") or ""),
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
            post_metadata = profile_metadata(db, post_author)
            serialized_post = {
                "id": getattr(post, "id", None),
                "title": getattr(post, "title", ""),
                "text": getattr(post, "description", ""),
                "userName": post_author,
                "userInitials": (post_author[:2]).upper() if post_author else "AI",
                "author_img": social_avatar(getattr(post, "author_img", "") or ""),
                "time": format_timestamp(getattr(post, "created_at", None)),
                "author_type": "ai",
                "profile_url": post_metadata.get("domain_url", ""),
                "domain_as_profile": bool(post_metadata.get("domain_as_profile", False)),
                "likes": [],
                "dislikes": [],
                "comments": [],
                "media": media_payload(
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
            return connector_action_response(action, summary, action.result_payload)
        except HTTPException:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to approve AI post action: {str(exc)}")

    return router
