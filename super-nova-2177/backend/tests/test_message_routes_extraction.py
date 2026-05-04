import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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
from backend.routers.messages import create_messages_router  # noqa: E402


class MessageRoutesExtractionTests(unittest.TestCase):
    def test_messages_routes_are_registered_from_dedicated_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "messages.py").read_text(encoding="utf-8")

        self.assertIn("from .routers.messages import create_messages_router", app_text)
        self.assertIn("app.include_router(create_messages_router(", app_text)
        self.assertNotIn('@app.get("/messages"', app_text)
        self.assertNotIn('@app.post("/messages"', app_text)
        self.assertIn('@router.get("/messages"', module_text)
        self.assertIn('@router.post("/messages"', module_text)

        registered = {
            (getattr(route, "path", ""), tuple(sorted(getattr(route, "methods", set()) or set())))
            for route in backend_app.app.routes
        }
        self.assertIn(("/messages", ("GET",)), registered)
        self.assertIn(("/messages", ("POST",)), registered)

    def test_messages_router_preserves_fallback_json_store_behavior(self):
        class DirectMessagePayload(BaseModel):
            sender: str
            recipient: str
            body: str

        class FakeDb:
            def __init__(self):
                self.rollbacks = 0

            def rollback(self):
                self.rollbacks += 1

        fake_db = FakeDb()
        store = []

        def get_db():
            yield fake_db

        def require_token_identity_match(authorization, db, requested_sender):
            if authorization != "Bearer ok":
                raise HTTPException(status_code=401, detail="Invalid token")
            return SimpleNamespace(username="alice")

        def canonical_username_from_alias(db, username):
            return {"ally": "alice", "bobby": "bob"}.get((username or "").strip().lower(), username)

        def ensure_direct_messages_table(db):
            raise RuntimeError("database unavailable")

        def read_messages_store():
            return list(store)

        def write_messages_store(messages):
            store[:] = list(messages)

        app = FastAPI()
        app.include_router(create_messages_router(
            get_db=get_db,
            direct_message_model=DirectMessagePayload,
            safe_user_key=lambda value: (value or "").strip().lower(),
            require_token_identity_match=require_token_identity_match,
            canonical_username_from_alias=canonical_username_from_alias,
            conversation_id=lambda left, right: "::".join(sorted([left.lower(), right.lower()])),
            ensure_direct_messages_table=ensure_direct_messages_table,
            message_payload=lambda row: dict(row),
            read_messages_store=read_messages_store,
            write_messages_store=write_messages_store,
        ))
        client = TestClient(app)

        created = client.post(
            "/messages",
            json={"sender": "ally", "recipient": "bobby", "body": " hello "},
            headers={"Authorization": "Bearer ok"},
        )
        self.assertEqual(created.status_code, 200)
        created_payload = created.json()
        self.assertEqual(
            set(created_payload.keys()),
            {"id", "conversation_id", "sender", "recipient", "body", "created_at"},
        )
        self.assertEqual(created_payload["sender"], "alice")
        self.assertEqual(created_payload["recipient"], "bob")
        self.assertEqual(created_payload["body"], "hello")
        self.assertEqual(len(store), 1)

        thread = client.get(
            "/messages?user=ally&peer=bobby",
            headers={"Authorization": "Bearer ok"},
        )
        self.assertEqual(thread.status_code, 200)
        self.assertEqual(thread.json()["peer"], "bob")
        self.assertEqual(thread.json()["messages"], store)

        conversations = client.get(
            "/messages?user=ally",
            headers={"Authorization": "Bearer ok"},
        )
        self.assertEqual(conversations.status_code, 200)
        self.assertEqual(conversations.json()["conversations"][0]["peer"], "bob")


if __name__ == "__main__":
    unittest.main()
