import re
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for path in (ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import backend.app as backend_app  # noqa: E402
from backend.routers.social_graph import create_social_graph_router  # noqa: E402


class FollowPayload(BaseModel):
    follower: str
    target: str


class FakeResult:
    def fetchall(self):
        return []


class FakeDb:
    def execute(self, *_args, **_kwargs):
        return FakeResult()

    def query(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return []


def _safe_user_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _create_test_client(initial_follows=None):
    follows_store = list(initial_follows or [])
    app = FastAPI()

    def get_db():
        return FakeDb()

    def collect_social_users(_db, limit=36, search=None):
        users = [
            {
                "username": "bob",
                "initials": "BO",
                "species": "human",
                "avatar": "",
                "domain_url": "",
                "domain_as_profile": False,
                "post_count": 2,
                "latest_post_id": 7,
                "can_collab": False,
            },
            {
                "username": "casey",
                "initials": "CA",
                "species": "org",
                "avatar": "",
                "domain_url": "",
                "domain_as_profile": False,
                "post_count": 1,
                "latest_post_id": 8,
                "can_collab": True,
            },
        ]
        if search:
            users = [user for user in users if search.lower() in user["username"].lower()]
        return users[:limit]

    def profile_metadata(_db, username):
        return {"domain_url": f"https://example.test/{username}", "domain_as_profile": True}

    def read_follows_store():
        return list(follows_store)

    def write_follows_store(next_follows):
        follows_store[:] = list(next_follows)

    def enforce_token_identity_match(_authorization, _db, _username):
        return None

    def require_token_identity_match(authorization, _db, username):
        if authorization != f"Bearer {_safe_user_key(username)}":
            raise HTTPException(status_code=401, detail="Missing or invalid token")
        return None

    app.include_router(create_social_graph_router(
        get_db=get_db,
        follow_model=FollowPayload,
        collect_social_users=collect_social_users,
        profile_metadata=profile_metadata,
        safe_user_key=_safe_user_key,
        social_avatar=lambda value: value or "",
        find_harmonizer_by_username=lambda _db, _username: None,
        read_follows_store=read_follows_store,
        write_follows_store=write_follows_store,
        enforce_token_identity_match=enforce_token_identity_match,
        require_token_identity_match=require_token_identity_match,
        proposal_model=None,
        comment_model=None,
        proposal_vote_model=None,
        crud_models_available=False,
        serialize_comment_record=lambda _db, _comment: {},
        serialize_vote_record=lambda _db, _vote: (None, None),
    ))
    return TestClient(app), follows_store


class SocialGraphRoutesExtractionTests(unittest.TestCase):
    def test_social_graph_routes_are_registered_from_dedicated_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "social_graph.py").read_text(encoding="utf-8")

        self.assertIn("from .routers.social_graph import create_social_graph_router", app_text)
        self.assertIn("app.include_router(create_social_graph_router(", app_text)
        for decorator in [
            '@app.get("/social-users"',
            '@app.get("/social-graph"',
            '@app.get("/follows"',
            '@app.get("/follows/status"',
            '@app.post("/follows"',
            '@app.delete("/follows"',
        ]:
            self.assertNotIn(decorator, app_text)
        for decorator in [
            '@router.get("/social-users"',
            '@router.get("/social-graph"',
            '@router.get("/follows"',
            '@router.get("/follows/status"',
            '@router.post("/follows"',
            '@router.delete("/follows"',
        ]:
            self.assertIn(decorator, module_text)

        registered = {}
        for route in backend_app.app.routes:
            path = getattr(route, "path", "")
            if path in {"/social-users", "/social-graph", "/follows", "/follows/status"}:
                registered.setdefault(path, set()).update(getattr(route, "methods", set()) or set())
        self.assertIn("GET", registered["/social-users"])
        self.assertIn("GET", registered["/social-graph"])
        self.assertIn("GET", registered["/follows"])
        self.assertIn("DELETE", registered["/follows"])
        self.assertIn("GET", registered["/follows/status"])
        self.assertIn("POST", registered["/follows"])

    def test_follow_routes_preserve_fallback_store_response_shapes(self):
        client, follows_store = _create_test_client()

        created = client.post(
            "/follows",
            json={"follower": "alice", "target": "bob"},
            headers={"Authorization": "Bearer alice"},
        )
        listed = client.get("/follows?user=alice")
        status = client.get("/follows/status?follower=alice&target=bob")
        duplicate = client.post(
            "/follows",
            json={"follower": "alice", "target": "bob"},
            headers={"Authorization": "Bearer alice"},
        )
        listed_after_duplicate = client.get("/follows?user=alice")
        deleted = client.delete(
            "/follows?follower=alice&target=bob",
            headers={"Authorization": "Bearer alice"},
        )
        listed_after_delete = client.get("/follows?user=alice")

        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json(), {"following": True, "follower": "alice", "target": "bob"})
        self.assertEqual(listed.json()["following"][0]["username"], "bob")
        self.assertEqual(status.json(), {"follower": "alice", "target": "bob", "following": True})
        self.assertEqual(duplicate.json(), {"following": True, "follower": "alice", "target": "bob"})
        self.assertEqual(len(listed_after_duplicate.json()["following"]), 1)
        self.assertEqual(deleted.json(), {"following": False, "follower": "alice", "target": "bob"})
        self.assertEqual(follows_store, [])
        self.assertEqual(listed_after_delete.json(), {"user": "alice", "following": [], "followers": []})

    def test_social_reads_preserve_public_shapes(self):
        follow = {
            "id": "follow-1",
            "follower": "alice",
            "follower_key": "alice",
            "target": "bob",
            "target_key": "bob",
            "created_at": "2026-05-04T00:00:00Z",
        }
        client, _store = _create_test_client([follow])

        users = client.get("/social-users?username=alice").json()
        graph = client.get("/social-graph?username=alice&limit=4").json()

        self.assertEqual(users[0]["username"], "alice")
        self.assertEqual(users[0]["species"], "human")
        self.assertEqual(users[0]["domain_url"], "https://example.test/alice")
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertIn("meta", graph)
        self.assertEqual(graph["meta"]["current_user"], "alice")
        self.assertGreaterEqual(graph["meta"]["node_count"], 2)
        self.assertTrue(any(edge["reasons"].get("follows") for edge in graph["edges"]))


if __name__ == "__main__":
    unittest.main()
