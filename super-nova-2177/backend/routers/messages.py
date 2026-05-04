import datetime
import uuid
from typing import Any, Callable, Dict, List, Optional, Type

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session


def create_messages_router(
    *,
    get_db: Callable,
    direct_message_model: Type[BaseModel],
    safe_user_key: Callable[[Optional[str]], str],
    require_token_identity_match: Callable,
    canonical_username_from_alias: Callable[[Session, Optional[str]], str],
    conversation_id: Callable[[str, str], str],
    ensure_direct_messages_table: Callable[[Session], None],
    message_payload: Callable[[Any], Dict[str, Any]],
    read_messages_store: Callable[[], List[Dict[str, Any]]],
    write_messages_store: Callable[[List[Dict[str, Any]]], None],
) -> APIRouter:
    router = APIRouter()

    @router.get("/messages", summary="Get direct messages or conversation summaries")
    def get_messages(
        user: str = Query(...),
        peer: Optional[str] = Query(None),
        limit: Optional[int] = Query(None),
        offset: int = Query(0),
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        current = safe_user_key(user)
        if not current:
            raise HTTPException(status_code=400, detail="user is required")
        current_user = require_token_identity_match(authorization, db, user)
        canonical_user = (
            getattr(current_user, "username", None)
            or canonical_username_from_alias(db, user)
            or user
        ).strip()
        current = safe_user_key(canonical_user)
        canonical_peer = canonical_username_from_alias(db, peer) if peer else None
        has_pagination = limit is not None
        safe_limit = max(1, min(int(limit), 500)) if has_pagination else None
        safe_offset = max(0, int(offset or 0))

        try:
            ensure_direct_messages_table(db)
            if canonical_peer:
                cid = conversation_id(canonical_user, canonical_peer)
                if has_pagination:
                    rows = db.execute(
                        text(
                            "SELECT id, conversation_id, sender, recipient, body, created_at "
                            "FROM direct_messages WHERE conversation_id = :cid "
                            "ORDER BY created_at ASC, id ASC LIMIT :limit OFFSET :offset"
                        ),
                        {"cid": cid, "limit": safe_limit, "offset": safe_offset},
                    ).fetchall()
                else:
                    rows = db.execute(
                        text(
                            "SELECT id, conversation_id, sender, recipient, body, created_at "
                            "FROM direct_messages WHERE conversation_id = :cid ORDER BY created_at ASC"
                        ),
                        {"cid": cid},
                    ).fetchall()
                return {"peer": canonical_peer, "messages": [message_payload(row) for row in rows]}

            rows = db.execute(
                text(
                    "SELECT id, conversation_id, sender, recipient, body, created_at "
                    "FROM direct_messages "
                    "WHERE lower(sender) = :current OR lower(recipient) = :current "
                    "ORDER BY created_at DESC LIMIT 1000"
                ),
                {"current": current},
            ).fetchall()
            conversations: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                message = message_payload(row)
                sender = safe_user_key(message.get("sender", ""))
                recipient = safe_user_key(message.get("recipient", ""))
                peer_name = message.get("sender") if recipient == current else message.get("recipient")
                key = safe_user_key(peer_name)
                if not key or key in conversations:
                    continue
                conversations[key] = {
                    "peer": peer_name,
                    "last_message": message,
                    "updated_at": message.get("created_at", ""),
                }

            sorted_conversations = sorted(
                conversations.values(),
                key=lambda item: item.get("updated_at", ""),
                reverse=True,
            )
            if has_pagination:
                sorted_conversations = sorted_conversations[safe_offset:safe_offset + safe_limit]
            return {"conversations": sorted_conversations}
        except Exception:
            db.rollback()

        messages = read_messages_store()
        if canonical_peer:
            cid = conversation_id(canonical_user, canonical_peer)
            thread = [message for message in messages if message.get("conversation_id") == cid]
            sorted_thread = sorted(thread, key=lambda item: item.get("created_at", ""))
            if has_pagination:
                sorted_thread = sorted_thread[safe_offset:safe_offset + safe_limit]
            return {"peer": canonical_peer, "messages": sorted_thread}

        conversations: Dict[str, Dict[str, Any]] = {}
        for message in messages:
            sender = safe_user_key(message.get("sender", ""))
            recipient = safe_user_key(message.get("recipient", ""))
            if current not in {sender, recipient}:
                continue
            peer_name = message.get("sender") if recipient == current else message.get("recipient")
            key = safe_user_key(peer_name)
            conversations[key] = {
                "peer": peer_name,
                "last_message": message,
                "updated_at": message.get("created_at", ""),
            }

        sorted_conversations = sorted(
            conversations.values(),
            key=lambda item: item.get("updated_at", ""),
            reverse=True,
        )
        if has_pagination:
            sorted_conversations = sorted_conversations[safe_offset:safe_offset + safe_limit]
        return {"conversations": sorted_conversations}

    @router.post("/messages", summary="Send a direct message")
    def send_message(
        payload: direct_message_model,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        requested_sender = payload.sender.strip()
        recipient = payload.recipient.strip()
        body = payload.body.strip()
        if not requested_sender:
            raise HTTPException(status_code=400, detail="sender is required")
        if not recipient:
            raise HTTPException(status_code=400, detail="recipient is required")
        current_user = require_token_identity_match(authorization, db, requested_sender)
        sender = (
            getattr(current_user, "username", None)
            or canonical_username_from_alias(db, requested_sender)
            or requested_sender
        ).strip()
        recipient = canonical_username_from_alias(db, recipient)
        if safe_user_key(sender) == safe_user_key(recipient):
            raise HTTPException(status_code=400, detail="Choose another user to message")
        if not body:
            raise HTTPException(status_code=400, detail="Write a message first")

        messages = read_messages_store()
        message = {
            "id": uuid.uuid4().hex,
            "conversation_id": conversation_id(sender, recipient),
            "sender": sender,
            "recipient": recipient,
            "body": body,
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        try:
            ensure_direct_messages_table(db)
            db.execute(
                text(
                    "INSERT INTO direct_messages "
                    "(id, conversation_id, sender, recipient, body, created_at) "
                    "VALUES (:id, :conversation_id, :sender, :recipient, :body, :created_at)"
                ),
                message,
            )
            db.commit()
            return message
        except Exception:
            db.rollback()

        messages.append(message)
        write_messages_store(messages[-1000:])
        return message

    return router
