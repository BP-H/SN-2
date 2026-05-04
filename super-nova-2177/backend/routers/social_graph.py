import datetime
import uuid
from typing import Any, Callable, Dict, List, Optional, Type

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, text
from sqlalchemy.orm import Session


def create_social_graph_router(
    *,
    get_db: Callable,
    follow_model: Type[BaseModel],
    collect_social_users: Callable,
    profile_metadata: Callable,
    safe_user_key: Callable[[Optional[str]], str],
    social_avatar: Callable[[str], str],
    find_harmonizer_by_username: Callable,
    read_follows_store: Callable[[], List[Dict[str, Any]]],
    write_follows_store: Callable[[List[Dict[str, Any]]], None],
    enforce_token_identity_match: Callable,
    require_token_identity_match: Callable,
    proposal_model,
    comment_model,
    proposal_vote_model,
    crud_models_available: bool,
    serialize_comment_record: Callable,
    serialize_vote_record: Callable,
) -> APIRouter:
    router = APIRouter()

    @router.get("/social-users", summary="List users available for social messaging")
    def social_users(
        username: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        limit: int = Query(36, ge=1, le=80),
        db: Session = Depends(get_db),
    ):
        users = collect_social_users(db, limit=limit, search=search)
        current = safe_user_key(username or "")
        if current and all(safe_user_key(item["username"]) != current for item in users):
            metadata = profile_metadata(db, username or "")
            users.insert(0, {
                "username": username,
                "initials": (username or "SN")[:2].upper(),
                "species": "human",
                "avatar": "",
                "domain_url": metadata.get("domain_url", ""),
                "domain_as_profile": bool(metadata.get("domain_as_profile", False)),
                "post_count": 0,
                "latest_post_id": 0,
                "can_collab": False,
            })
        return users

    @router.get("/social-graph", summary="Desktop social constellation graph")
    def social_graph(
        username: Optional[str] = Query(None),
        limit: int = Query(14, ge=4, le=96),
        db: Session = Depends(get_db),
    ):
        current_key = safe_user_key(username or "")
        graph_scan_limit = min(max(limit * 4, 80), 320)
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: Dict[str, Dict[str, Any]] = {}

        def ensure_node(name: str, species: str = "human", avatar: str = "", activity: int = 0) -> str:
            clean_name = (name or "").strip()
            key = safe_user_key(clean_name)
            if not key:
                return ""
            existing = nodes.get(key)
            if not existing:
                existing = {
                    "id": key,
                    "username": clean_name,
                    "display_name": clean_name,
                    "species": species or "human",
                    "avatar_url": social_avatar(avatar),
                    "activity_score": 0,
                    "is_current": bool(current_key and key == current_key),
                }
                nodes[key] = existing
            existing["activity_score"] = int(existing.get("activity_score", 0)) + max(0, int(activity or 0))
            if avatar and not existing.get("avatar_url"):
                existing["avatar_url"] = social_avatar(avatar)
            if species and existing.get("species") == "human":
                existing["species"] = species
            return key

        def add_edge(source: str, target: str, amount: int, reason: str) -> None:
            source_key = safe_user_key(source)
            target_key = safe_user_key(target)
            if not source_key or not target_key or source_key == target_key:
                return
            if source_key not in nodes or target_key not in nodes:
                return
            edge_key = "::".join(sorted([source_key, target_key]))
            edge = edges.get(edge_key)
            if not edge:
                edge = {
                    "id": edge_key,
                    "source": source_key,
                    "target": target_key,
                    "strength": 0,
                    "reasons": {"comments": 0, "replies": 0, "votes": 0, "follows": 0, "messages": 0},
                }
                edges[edge_key] = edge
            edge["strength"] = int(edge.get("strength", 0)) + amount
            reasons = edge.setdefault("reasons", {})
            reasons[reason] = int(reasons.get(reason, 0)) + 1

        for user in collect_social_users(db, limit=max(limit * 3, 36)):
            ensure_node(
                user.get("username", ""),
                user.get("species", "human"),
                user.get("avatar", ""),
                int(user.get("post_count", 0)) * 3,
            )

        if username and current_key not in nodes:
            user = find_harmonizer_by_username(db, username)
            ensure_node(
                username,
                getattr(user, "species", "human") if user else "human",
                getattr(user, "profile_pic", "") if user else "",
                4,
            )

        try:
            for item in read_follows_store()[-1000:]:
                follower = item.get("follower", "")
                target = item.get("target", "")
                ensure_node(follower, "human", "", 4)
                ensure_node(target, "human", "", 4)
                add_edge(follower, target, 8, "follows")
        except Exception:
            pass

        try:
            proposals = []
            if proposal_model is not None:
                proposals = db.query(proposal_model).order_by(desc(proposal_model.id)).limit(graph_scan_limit).all()
            else:
                proposals = db.execute(
                    text("SELECT id, userName, author_type, author_img FROM proposals ORDER BY id DESC LIMIT :limit"),
                    {"limit": graph_scan_limit},
                ).fetchall()

            for proposal in proposals:
                proposal_id = getattr(proposal, "id", None)
                author = getattr(proposal, "userName", None) or getattr(proposal, "author", None) or "Unknown"
                author_species = getattr(proposal, "author_type", None) or "human"
                author_avatar = getattr(proposal, "author_img", None) or ""
                ensure_node(author, author_species, author_avatar, 5)

                try:
                    comments = (
                        db.query(comment_model).filter(comment_model.proposal_id == proposal_id).limit(120).all()
                        if crud_models_available
                        else db.execute(
                            text("SELECT * FROM comments WHERE proposal_id = :pid LIMIT 120"),
                            {"pid": proposal_id},
                        ).fetchall()
                    )
                except Exception:
                    comments = []
                comments_by_id = {}
                for comment in comments[:120]:
                    payload = serialize_comment_record(db, comment)
                    comments_by_id[str(payload.get("id"))] = payload
                    if payload.get("deleted"):
                        continue
                    commenter = payload.get("user", "")
                    ensure_node(commenter, payload.get("species", "human"), payload.get("user_img", ""), 3)
                    add_edge(commenter, author, 5, "comments")
                    parent_id = payload.get("parent_comment_id")
                    parent = comments_by_id.get(str(parent_id)) if parent_id is not None else None
                    if parent and not parent.get("deleted"):
                        add_edge(commenter, parent.get("user", ""), 4, "replies")

                try:
                    votes = (
                        db.query(proposal_vote_model)
                        .filter(proposal_vote_model.proposal_id == proposal_id)
                        .limit(120)
                        .all()
                        if crud_models_available
                        else db.execute(
                            text("SELECT * FROM proposal_votes WHERE proposal_id = :pid LIMIT 120"),
                            {"pid": proposal_id},
                        ).fetchall()
                    )
                except Exception:
                    votes = []
                vote_entries = []
                for vote in votes[:120]:
                    like_entry, dislike_entry = serialize_vote_record(db, vote)
                    entry = like_entry or dislike_entry
                    if not entry:
                        continue
                    voter = entry.get("voter", "")
                    ensure_node(voter, entry.get("type", "human"), "", 2)
                    add_edge(voter, author, 2, "votes")
                    vote_entries.append((voter, bool(like_entry)))
                for index, (left_user, left_choice) in enumerate(vote_entries[:24]):
                    for right_user, right_choice in vote_entries[index + 1:24]:
                        add_edge(left_user, right_user, 3 if left_choice == right_choice else 2, "votes")
        except Exception:
            pass

        try:
            rows = db.execute(
                text("SELECT sender, recipient FROM direct_messages ORDER BY created_at DESC LIMIT :limit"),
                {"limit": min(max(limit * 4, 160), 360)},
            ).fetchall()
            for row in rows:
                data = getattr(row, "_mapping", row)
                ensure_node(data["sender"], "human", "", 2)
                ensure_node(data["recipient"], "human", "", 2)
                add_edge(data["sender"], data["recipient"], 6, "messages")
        except Exception:
            pass

        ordered_nodes = sorted(
            nodes.values(),
            key=lambda node: (not node.get("is_current"), -int(node.get("activity_score", 0)), node.get("username", "")),
        )[:limit]
        allowed = {node["id"] for node in ordered_nodes}
        ordered_edges = sorted(
            [edge for edge in edges.values() if edge["source"] in allowed and edge["target"] in allowed],
            key=lambda edge: int(edge.get("strength", 0)),
            reverse=True,
        )[:max(18, limit * 2)]
        return {
            "nodes": ordered_nodes,
            "edges": ordered_edges,
            "meta": {
                "node_count": len(ordered_nodes),
                "edge_count": len(ordered_edges),
                "current_user": current_key,
                "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            },
        }

    @router.get("/follows", summary="List follow relationships for a user")
    def get_follows(
        user: str = Query(...),
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        current = safe_user_key(user)
        if not current:
            raise HTTPException(status_code=400, detail="user is required")
        enforce_token_identity_match(authorization, db, user)
        follows = read_follows_store()
        following = [
            {"username": item.get("target", ""), "created_at": item.get("created_at", "")}
            for item in follows
            if item.get("follower_key") == current
        ]
        followers = [
            {"username": item.get("follower", ""), "created_at": item.get("created_at", "")}
            for item in follows
            if item.get("target_key") == current
        ]
        return {"user": user, "following": following, "followers": followers}

    @router.get("/follows/status", summary="Check if one user follows another")
    def follow_status(
        follower: str = Query(...),
        target: str = Query(...),
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        follower_key = safe_user_key(follower)
        target_key = safe_user_key(target)
        if not follower_key or not target_key:
            raise HTTPException(status_code=400, detail="follower and target are required")
        enforce_token_identity_match(authorization, db, follower)
        follows = read_follows_store()
        return {
            "follower": follower,
            "target": target,
            "following": any(
                item.get("follower_key") == follower_key and item.get("target_key") == target_key
                for item in follows
            ),
        }

    @router.post("/follows", summary="Follow a user")
    def follow_user(
        payload: follow_model,
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        follower = payload.follower.strip()
        target = payload.target.strip()
        follower_key = safe_user_key(follower)
        target_key = safe_user_key(target)
        if not follower_key or not target_key:
            raise HTTPException(status_code=400, detail="follower and target are required")
        if follower_key == target_key:
            raise HTTPException(status_code=400, detail="Choose another user to follow")
        require_token_identity_match(authorization, db, follower)

        follows = read_follows_store()
        existing = next(
            (
                item for item in follows
                if item.get("follower_key") == follower_key and item.get("target_key") == target_key
            ),
            None,
        )
        if existing:
            return {"following": True, "follower": follower, "target": target}

        follows.append({
            "id": uuid.uuid4().hex,
            "follower": follower,
            "follower_key": follower_key,
            "target": target,
            "target_key": target_key,
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        })
        write_follows_store(follows[-5000:])
        return {"following": True, "follower": follower, "target": target}

    @router.delete("/follows", summary="Unfollow a user")
    def unfollow_user(
        follower: str = Query(...),
        target: str = Query(...),
        authorization: Optional[str] = Header(default=None),
        db: Session = Depends(get_db),
    ):
        follower_key = safe_user_key(follower)
        target_key = safe_user_key(target)
        if not follower_key or not target_key:
            raise HTTPException(status_code=400, detail="follower and target are required")
        require_token_identity_match(authorization, db, follower)
        follows = read_follows_store()
        next_follows = [
            item for item in follows
            if not (item.get("follower_key") == follower_key and item.get("target_key") == target_key)
        ]
        write_follows_store(next_follows)
        return {"following": False, "follower": follower, "target": target}

    return router
