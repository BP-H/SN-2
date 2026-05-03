import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_auth_probe(probe: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "auth_bound_write_routes.sqlite"
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() != "SUPERNOVA_ACCESS_TOKEN_MINUTES"
        }
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": "strong-test-secret-for-auth-bound-write-routes",
                "SUPERNOVA_ACCESS_TOKEN_MINUTES": "720",
                "SUPERNOVA_ENV": "development",
                "APP_ENV": "development",
                "ENV": "development",
                "UPLOADS_DIR": str(Path(tmpdir) / "uploads"),
                "FOLLOWS_STORE_PATH": str(Path(tmpdir) / "follows_store.json"),
            }
        )
        env.pop("RAILWAY_ENVIRONMENT", None)

        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    if completed.returncode != 0:
        raise AssertionError(
            f"probe failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    result_lines = [
        line
        for line in completed.stdout.splitlines()
        if line.startswith("AUTH_BOUND_WRITE_ROUTES_RESULT=")
    ]
    if not result_lines:
        raise AssertionError(f"probe result missing\nstdout:\n{completed.stdout}")
    return json.loads(result_lines[-1].split("=", 1)[1])


PROBE_PREAMBLE = """
import datetime
import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

project_root = Path.cwd()
backend_dir = project_root / "backend"
for path in (project_root, backend_dir):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

os.environ["SUPERNOVA_ACCESS_TOKEN_MINUTES"] = "720"

import backend.app as backend_app
from db_models import Base

backend_app.FOLLOWS_STORE_PATH = Path(os.environ["FOLLOWS_STORE_PATH"])
client = TestClient(backend_app.app)


def current_bind():
    session = backend_app.SessionLocal()
    try:
        return session.get_bind()
    finally:
        session.close()


Base.metadata.create_all(bind=current_bind())


def seed_users():
    db = backend_app.SessionLocal()
    try:
        alice = backend_app.Harmonizer(
            username="alice",
            email="alice@example.test",
            hashed_password="test",
            bio="original",
            species="human",
            profile_pic="default.jpg",
        )
        bob = backend_app.Harmonizer(
            username="bob",
            email="bob@example.test",
            hashed_password="test",
            bio="other",
            species="ai",
            profile_pic="default.jpg",
        )
        cara = backend_app.Harmonizer(
            username="cara",
            email="cara@example.test",
            hashed_password="test",
            bio="third",
            species="company",
            profile_pic="default.jpg",
        )
        db.add_all([alice, bob, cara])
        db.commit()
        backend_app._ensure_direct_messages_table(db)
        rows = [
            {
                "id": "msg-1",
                "conversation_id": backend_app._conversation_id("alice", "bob"),
                "sender": "alice",
                "recipient": "bob",
                "body": "hello bob",
                "created_at": "2026-01-01T12:00:00Z",
            },
            {
                "id": "msg-2",
                "conversation_id": backend_app._conversation_id("bob", "alice"),
                "sender": "bob",
                "recipient": "alice",
                "body": "hello alice",
                "created_at": "2026-01-01T12:01:00Z",
            },
        ]
        for row in rows:
            db.execute(
                text(
                    "INSERT INTO direct_messages "
                    "(id, conversation_id, sender, recipient, body, created_at) "
                    "VALUES (:id, :conversation_id, :sender, :recipient, :body, :created_at)"
                ),
                row,
            )
        db.commit()
    finally:
        db.close()


seed_users()
upload_dir = Path(os.environ["UPLOADS_DIR"])
alice_token = backend_app._create_wrapper_access_token("alice")
bob_token = backend_app._create_wrapper_access_token("bob")
cara_token = backend_app._create_wrapper_access_token("cara")
alice_headers = {"Authorization": f"Bearer {alice_token}"}
bob_headers = {"Authorization": f"Bearer {bob_token}"}
cara_headers = {"Authorization": f"Bearer {cara_token}"}
invalid_headers = {"Authorization": "Bearer not-a-valid-token"}


def uploaded_files():
    if not upload_dir.exists():
        return []
    return sorted(item.name for item in upload_dir.iterdir() if item.is_file())


def profile_pic_for(username):
    db = backend_app.SessionLocal()
    try:
        user = db.query(backend_app.Harmonizer).filter(
            backend_app.func.lower(backend_app.Harmonizer.username) == username.lower()
        ).first()
        return getattr(user, "profile_pic", "") if user else ""
    finally:
        db.close()


def user_id_for(username):
    db = backend_app.SessionLocal()
    try:
        user = db.query(backend_app.Harmonizer).filter(
            backend_app.func.lower(backend_app.Harmonizer.username) == username.lower()
        ).first()
        return getattr(user, "id", None)
    finally:
        db.close()


def harmonizer_count_for(username):
    db = backend_app.SessionLocal()
    try:
        return db.query(backend_app.Harmonizer).filter(
            backend_app.func.lower(backend_app.Harmonizer.username) == username.lower()
        ).count()
    finally:
        db.close()


def seed_comment_target(author="alice", proposal_owner="bob", content="original comment"):
    db = backend_app.SessionLocal()
    try:
        author_obj = db.query(backend_app.Harmonizer).filter(
            backend_app.func.lower(backend_app.Harmonizer.username) == author.lower()
        ).first()
        owner_obj = db.query(backend_app.Harmonizer).filter(
            backend_app.func.lower(backend_app.Harmonizer.username) == proposal_owner.lower()
        ).first()
        node = backend_app.VibeNode(
            name=f"comment-auth-node-{author}-{proposal_owner}",
            author_id=owner_obj.id,
        )
        proposal = backend_app.Proposal(
            title="Comment auth proposal",
            description="Pins comment edit/delete auth behavior.",
            userName=proposal_owner,
            userInitials=proposal_owner[:2].upper(),
            author_type="human",
            author_id=owner_obj.id,
            voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        )
        db.add_all([node, proposal])
        db.commit()
        db.refresh(node)
        db.refresh(proposal)
        comment = backend_app.Comment(
            content=content,
            author_id=author_obj.id,
            vibenode_id=node.id,
            proposal_id=proposal.id,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(comment)
        db.commit()
        db.refresh(comment)
        return {"proposal_id": proposal.id, "comment_id": comment.id}
    finally:
        db.close()
"""


class AuthBoundWriteRouteTests(unittest.TestCase):
    def test_backend_session_tokens_last_long_enough_for_messages(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            payload = backend_app.jwt.decode(
                alice_token,
                backend_app.get_settings().SECRET_KEY,
                algorithms=[backend_app.get_settings().ALGORITHM],
            )
            ttl_seconds = int(payload.get("exp", 0)) - int(datetime.datetime.now(datetime.timezone.utc).timestamp())
            result = {
                "subject": payload.get("sub"),
                "ttl_minutes": ttl_seconds // 60,
                "configured_minutes": backend_app.WRAPPER_ACCESS_TOKEN_MINUTES,
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["subject"], "alice")
        self.assertGreaterEqual(result["ttl_minutes"], 600)
        self.assertGreaterEqual(result["configured_minutes"], 720)

    def test_profile_rename_returns_fresh_token_for_messages(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            rename = client.patch("/profile/alice", json={"username": "stellar"}, headers=alice_headers)
            new_token = rename.json().get("access_token")
            new_headers = {"Authorization": f"Bearer {new_token}"}
            sent = client.post(
                "/messages",
                json={"sender": "stellar", "recipient": "bob", "body": "hello after rename"},
                headers=new_headers,
            )
            thread = client.get("/messages?user=stellar&peer=bob", headers=new_headers)
            old_token_send = client.post(
                "/messages",
                json={"sender": "stellar", "recipient": "bob", "body": "old token should fail"},
                headers=alice_headers,
            )
            payload = sent.json()
            result = {
                "rename_status": rename.status_code,
                "rename_username": rename.json().get("username"),
                "has_new_token": bool(new_token),
                "sent_status": sent.status_code,
                "sent_sender": payload.get("sender"),
                "thread_status": thread.status_code,
                "thread_count": len(thread.json().get("messages", [])),
                "old_token_status": old_token_send.status_code,
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["rename_status"], 200)
        self.assertEqual(result["rename_username"], "stellar")
        self.assertTrue(result["has_new_token"])
        self.assertEqual(result["sent_status"], 200)
        self.assertEqual(result["sent_sender"], "stellar")
        self.assertEqual(result["thread_status"], 200)
        self.assertEqual(result["thread_count"], 3)
        self.assertEqual(result["old_token_status"], 401)

    def test_profile_update_requires_matching_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            missing = client.patch("/profile/alice", json={"bio": "missing token"})
            invalid = client.patch("/profile/alice", json={"bio": "invalid token"}, headers=invalid_headers)
            wrong = client.patch("/profile/alice", json={"bio": "wrong token"}, headers=bob_headers)
            after_failed = client.get("/profile/alice")
            matching = client.patch("/profile/alice", json={"bio": "updated bio"}, headers=alice_headers)
            public_read = client.get("/profile/alice")
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "after_failed_bio": after_failed.json().get("bio"),
                "matching_status": matching.status_code,
                "matching_username": matching.json().get("username"),
                "matching_bio": matching.json().get("bio"),
                "public_read_status": public_read.status_code,
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["after_failed_bio"], "original")
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(result["matching_username"], "alice")
        self.assertEqual(result["matching_bio"], "updated bio")
        self.assertEqual(result["public_read_status"], 200)

    def test_message_reads_require_matching_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            missing = client.get("/messages?user=alice")
            invalid = client.get("/messages?user=alice", headers=invalid_headers)
            wrong = client.get("/messages?user=alice", headers=bob_headers)
            matching = client.get("/messages?user=alice", headers=alice_headers)
            peer_missing = client.get("/messages?user=alice&peer=bob")
            peer_invalid = client.get("/messages?user=alice&peer=bob", headers=invalid_headers)
            peer_wrong = client.get("/messages?user=alice&peer=bob", headers=bob_headers)
            peer_matching = client.get("/messages?user=alice&peer=bob", headers=alice_headers)
            payload = matching.json()
            conversations = payload.get("conversations", [])
            peer_payload = peer_matching.json()
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "matching_status": matching.status_code,
                "peer_missing_status": peer_missing.status_code,
                "peer_invalid_status": peer_invalid.status_code,
                "peer_wrong_status": peer_wrong.status_code,
                "peer_matching_status": peer_matching.status_code,
                "keys": sorted(payload.keys()),
                "conversation_count": len(conversations),
                "first_peer": conversations[0].get("peer") if conversations else "",
                "last_message_keys": sorted(conversations[0].get("last_message", {}).keys()) if conversations else [],
                "peer_keys": sorted(peer_payload.keys()),
                "peer_count": len(peer_payload.get("messages", [])),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(result["peer_missing_status"], 401)
        self.assertEqual(result["peer_invalid_status"], 401)
        self.assertEqual(result["peer_wrong_status"], 403)
        self.assertEqual(result["peer_matching_status"], 200)
        self.assertEqual(result["keys"], ["conversations"])
        self.assertEqual(result["conversation_count"], 1)
        self.assertEqual(result["first_peer"], "bob")
        self.assertEqual(
            set(result["last_message_keys"]),
            {"body", "conversation_id", "created_at", "id", "recipient", "sender"},
        )
        self.assertEqual(set(result["peer_keys"]), {"messages", "peer"})
        self.assertEqual(result["peer_count"], 2)

    def test_message_writes_require_matching_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            body = {"sender": "alice", "recipient": "bob", "body": "secure hello"}
            missing = client.post("/messages", json=body)
            invalid = client.post("/messages", json=body, headers=invalid_headers)
            wrong = client.post("/messages", json=body, headers=bob_headers)
            after_failed_read = client.get("/messages?user=alice&peer=bob", headers=alice_headers)
            matching = client.post("/messages", json=body, headers=alice_headers)
            after_matching_read = client.get("/messages?user=alice&peer=bob", headers=alice_headers)
            payload = matching.json()
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "after_failed_count": len(after_failed_read.json().get("messages", [])),
                "matching_status": matching.status_code,
                "after_matching_count": len(after_matching_read.json().get("messages", [])),
                "keys": sorted(payload.keys()),
                "sender": payload.get("sender"),
                "recipient": payload.get("recipient"),
                "body": payload.get("body"),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["after_failed_count"], 2)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(result["after_matching_count"], 3)
        self.assertEqual(
            set(result["keys"]),
            {"body", "conversation_id", "created_at", "id", "recipient", "sender"},
        )
        self.assertEqual(result["sender"], "alice")
        self.assertEqual(result["recipient"], "bob")
        self.assertEqual(result["body"], "secure hello")

    def test_raw_image_upload_without_profile_sync_still_succeeds(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            response = client.post(
                "/upload-image",
                files={"file": ("raw.png", b"small-image", "image/png")},
            )
            payload = response.json()
            result = {
                "status_code": response.status_code,
                "keys": sorted(payload.keys()),
                "filename": payload.get("filename", ""),
                "url": payload.get("url", ""),
                "profile_synced": payload.get("profile_synced"),
                "files": uploaded_files(),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(
            set(result["keys"]),
            {"content_type", "filename", "profile_synced", "sync_error", "url"},
        )
        self.assertTrue(result["filename"].endswith(".png"))
        self.assertEqual(result["url"], f"/uploads/{result['filename']}")
        self.assertFalse(result["profile_synced"])
        self.assertEqual(result["files"], [result["filename"]])

    def test_upload_image_username_profile_sync_requires_matching_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            missing = client.post(
                "/upload-image",
                data={"username": "alice"},
                files={"file": ("missing.png", b"small-image", "image/png")},
            )
            invalid = client.post(
                "/upload-image",
                data={"username": "alice"},
                files={"file": ("invalid.png", b"small-image", "image/png")},
                headers=invalid_headers,
            )
            wrong = client.post(
                "/upload-image",
                data={"username": "alice"},
                files={"file": ("wrong.png", b"small-image", "image/png")},
                headers=bob_headers,
            )
            failed_profile_pic = profile_pic_for("alice")
            failed_files = uploaded_files()
            matching = client.post(
                "/upload-image",
                data={"username": "alice"},
                files={"file": ("matching.png", b"small-image", "image/png")},
                headers=alice_headers,
            )
            payload = matching.json()
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "failed_profile_pic": failed_profile_pic,
                "failed_files": failed_files,
                "matching_status": matching.status_code,
                "keys": sorted(payload.keys()),
                "profile_synced": payload.get("profile_synced"),
                "url": payload.get("url"),
                "profile_pic": profile_pic_for("alice"),
                "files": uploaded_files(),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["failed_profile_pic"], "default.jpg")
        self.assertEqual(result["failed_files"], [])
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(
            set(result["keys"]),
            {"content_type", "filename", "profile_synced", "sync_error", "url"},
        )
        self.assertTrue(result["profile_synced"])
        self.assertEqual(result["profile_pic"], result["url"])
        self.assertEqual(len(result["files"]), 1)

    def test_upload_image_user_id_profile_sync_requires_matching_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            alice_id = user_id_for("alice")
            missing = client.post(
                "/upload-image",
                data={"user_id": str(alice_id)},
                files={"file": ("missing.png", b"small-image", "image/png")},
            )
            invalid = client.post(
                "/upload-image",
                data={"user_id": str(alice_id)},
                files={"file": ("invalid.png", b"small-image", "image/png")},
                headers=invalid_headers,
            )
            wrong = client.post(
                "/upload-image",
                data={"user_id": str(alice_id)},
                files={"file": ("wrong.png", b"small-image", "image/png")},
                headers=bob_headers,
            )
            failed_profile_pic = profile_pic_for("alice")
            failed_files = uploaded_files()
            matching = client.post(
                "/upload-image",
                data={"user_id": str(alice_id)},
                files={"file": ("matching.png", b"small-image", "image/png")},
                headers=alice_headers,
            )
            payload = matching.json()
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "failed_profile_pic": failed_profile_pic,
                "failed_files": failed_files,
                "matching_status": matching.status_code,
                "profile_synced": payload.get("profile_synced"),
                "url": payload.get("url"),
                "profile_pic": profile_pic_for("alice"),
                "files": uploaded_files(),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["failed_profile_pic"], "default.jpg")
        self.assertEqual(result["failed_files"], [])
        self.assertEqual(result["matching_status"], 200)
        self.assertTrue(result["profile_synced"])
        self.assertEqual(result["profile_pic"], result["url"])
        self.assertEqual(len(result["files"]), 1)

    def test_follow_requires_matching_bearer_identity_and_public_read_remains_open(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            body = {"follower": "alice", "target": "bob"}
            missing = client.post("/follows", json=body)
            invalid = client.post("/follows", json=body, headers=invalid_headers)
            wrong = client.post("/follows", json=body, headers=bob_headers)
            matching = client.post("/follows", json=body, headers=alice_headers)
            payload = matching.json()
            public_read = client.get("/follows?user=alice")
            public_payload = public_read.json()
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "matching_status": matching.status_code,
                "keys": sorted(payload.keys()),
                "following": payload.get("following"),
                "follower": payload.get("follower"),
                "target": payload.get("target"),
                "public_read_status": public_read.status_code,
                "public_read_keys": sorted(public_payload.keys()),
                "public_following": public_payload.get("following", []),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(set(result["keys"]), {"follower", "following", "target"})
        self.assertTrue(result["following"])
        self.assertEqual(result["follower"], "alice")
        self.assertEqual(result["target"], "bob")
        self.assertEqual(result["public_read_status"], 200)
        self.assertEqual(set(result["public_read_keys"]), {"followers", "following", "user"})
        self.assertEqual(len(result["public_following"]), 1)
        self.assertEqual(result["public_following"][0]["username"], "bob")
        self.assertIn("created_at", result["public_following"][0])

    def test_unfollow_requires_matching_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            body = {"follower": "alice", "target": "bob"}
            client.post("/follows", json=body, headers=alice_headers)
            missing = client.delete("/follows?follower=alice&target=bob")
            invalid = client.delete("/follows?follower=alice&target=bob", headers=invalid_headers)
            wrong = client.delete("/follows?follower=alice&target=bob", headers=bob_headers)
            matching = client.delete("/follows?follower=alice&target=bob", headers=alice_headers)
            payload = matching.json()
            after = client.get("/follows?user=alice")
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "matching_status": matching.status_code,
                "keys": sorted(payload.keys()),
                "following": payload.get("following"),
                "follower": payload.get("follower"),
                "target": payload.get("target"),
                "after_following": after.json().get("following", []),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(set(result["keys"]), {"follower", "following", "target"})
        self.assertFalse(result["following"])
        self.assertEqual(result["follower"], "alice")
        self.assertEqual(result["target"], "bob")
        self.assertEqual(result["after_following"], [])

    def test_proposal_create_requires_matching_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            form = {
                "title": "Authenticated proposal",
                "body": "Proposal create should require a matching token.",
                "author": "alice",
                "author_type": "human",
            }
            missing = client.post("/proposals", data=form)
            invalid = client.post("/proposals", data=form, headers=invalid_headers)
            wrong = client.post("/proposals", data=form, headers=bob_headers)
            matching = client.post("/proposals", data=form, headers=alice_headers)
            payload = matching.json()
            public_read = client.get("/proposals?filter=latest&author=alice&limit=10")
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "matching_status": matching.status_code,
                "keys": sorted(payload.keys()),
                "title": payload.get("title"),
                "text": payload.get("text"),
                "userName": payload.get("userName"),
                "author_type": payload.get("author_type"),
                "public_read_status": public_read.status_code,
                "public_read_count": len(public_read.json()),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(
            set(result["keys"]),
            {
                "author_img",
                "author_type",
                "comments",
                "dislikes",
                "domain_as_profile",
                "id",
                "likes",
                "media",
                "profile_url",
                "text",
                "time",
                "title",
                "userInitials",
                "userName",
            },
        )
        self.assertEqual(result["title"], "Authenticated proposal")
        self.assertEqual(result["text"], "Proposal create should require a matching token.")
        self.assertEqual(result["userName"], "alice")
        self.assertEqual(result["author_type"], "human")
        self.assertEqual(result["public_read_status"], 200)
        self.assertGreaterEqual(result["public_read_count"], 1)

    def test_comment_create_requires_matching_bearer_identity_and_preserves_replies(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comment_target(author="alice", proposal_owner="bob")
            proposal_id = seeded["proposal_id"]
            parent_id = seeded["comment_id"]
            body = {
                "proposal_id": proposal_id,
                "user": "alice",
                "species": "human",
                "comment": "secure comment",
            }
            ghost_before = harmonizer_count_for("ghost-commenter")
            missing_unknown = client.post(
                "/comments",
                json={
                    "proposal_id": proposal_id,
                    "user": "ghost-commenter",
                    "species": "human",
                    "comment": "should not create fallback user",
                },
            )
            ghost_after = harmonizer_count_for("ghost-commenter")
            missing = client.post("/comments", json=body)
            invalid = client.post("/comments", json=body, headers=invalid_headers)
            wrong = client.post("/comments", json=body, headers=bob_headers)
            matching = client.post("/comments", json=body, headers=alice_headers)
            reply = client.post(
                "/comments",
                json={
                    "proposal_id": proposal_id,
                    "user": "alice",
                    "species": "human",
                    "comment": "secure reply",
                    "parent_comment_id": parent_id,
                },
                headers=alice_headers,
            )
            matching_payload = matching.json()
            reply_payload = reply.json()
            public_read = client.get(f"/comments?proposal_id={proposal_id}")
            public_payload = public_read.json()
            result = {
                "missing_unknown_status": missing_unknown.status_code,
                "ghost_before": ghost_before,
                "ghost_after": ghost_after,
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "matching_status": matching.status_code,
                "matching_keys": sorted(matching_payload.keys()),
                "matching_comment_keys": sorted(matching_payload.get("comments", [{}])[0].keys()),
                "matching_comment": matching_payload.get("comments", [{}])[0].get("comment"),
                "matching_user": matching_payload.get("comments", [{}])[0].get("user"),
                "reply_status": reply.status_code,
                "parent_id": parent_id,
                "reply_parent": reply_payload.get("comments", [{}])[0].get("parent_comment_id"),
                "public_read_status": public_read.status_code,
                "public_count": len(public_payload),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_unknown_status"], 401)
        self.assertEqual(result["ghost_before"], 0)
        self.assertEqual(result["ghost_after"], 0)
        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(set(result["matching_keys"]), {"comments", "ok", "species"})
        self.assertEqual(
            set(result["matching_comment_keys"]),
            {
                "comment",
                "created_at",
                "deleted",
                "id",
                "parent_comment_id",
                "proposal_id",
                "likes",
                "dislikes",
                "species",
                "user",
                "user_img",
            },
        )
        self.assertEqual(result["matching_comment"], "secure comment")
        self.assertEqual(result["matching_user"], "alice")
        self.assertEqual(result["reply_status"], 200)
        self.assertEqual(result["reply_parent"], result["parent_id"])
        self.assertEqual(result["public_read_status"], 200)
        self.assertGreaterEqual(result["public_count"], 3)

    def test_comment_edit_requires_matching_author_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comment_target(author="alice", proposal_owner="bob")
            comment_id = seeded["comment_id"]
            proposal_id = seeded["proposal_id"]
            missing = client.patch(
                f"/comments/{comment_id}",
                json={"user": "alice", "comment": "missing token"},
            )
            invalid = client.patch(
                f"/comments/{comment_id}",
                json={"user": "alice", "comment": "invalid token"},
                headers=invalid_headers,
            )
            wrong = client.patch(
                f"/comments/{comment_id}",
                json={"user": "alice", "comment": "wrong token"},
                headers=bob_headers,
            )
            matching = client.patch(
                f"/comments/{comment_id}",
                json={"user": "alice", "comment": "edited by alice"},
                headers=alice_headers,
            )
            payload = matching.json()
            public_read = client.get(f"/comments?proposal_id={proposal_id}")
            public_payload = public_read.json()
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "matching_status": matching.status_code,
                "keys": sorted(payload.keys()),
                "comment": payload.get("comment"),
                "user": payload.get("user"),
                "public_read_status": public_read.status_code,
                "public_count": len(public_payload),
                "public_comment": public_payload[0].get("comment") if public_payload else "",
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(
            set(result["keys"]),
            {
                "comment",
                "created_at",
                "deleted",
                "id",
                "parent_comment_id",
                "proposal_id",
                "likes",
                "dislikes",
                "species",
                "user",
                "user_img",
            },
        )
        self.assertEqual(result["comment"], "edited by alice")
        self.assertEqual(result["user"], "alice")
        self.assertEqual(result["public_read_status"], 200)
        self.assertEqual(result["public_count"], 1)
        self.assertEqual(result["public_comment"], "edited by alice")

    def test_comment_votes_are_auth_bound_and_publicly_serialized(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comment_target(author="alice", proposal_owner="alice")
            comment_id = seeded["comment_id"]
            proposal_id = seeded["proposal_id"]
            missing = client.post(
                f"/comments/{comment_id}/votes",
                json={"username": "bob", "choice": "up", "voter_type": "human"},
            )
            wrong = client.post(
                f"/comments/{comment_id}/votes",
                json={"username": "bob", "choice": "up", "voter_type": "human"},
                headers=alice_headers,
            )
            voted = client.post(
                f"/comments/{comment_id}/votes",
                json={"username": "bob", "choice": "up", "voter_type": "human"},
                headers=bob_headers,
            )
            public_read = client.get(f"/comments?proposal_id={proposal_id}")
            removed = client.delete(f"/comments/{comment_id}/votes?username=bob", headers=bob_headers)
            public_after_remove = client.get(f"/comments?proposal_id={proposal_id}")
            result = {
                "missing_status": missing.status_code,
                "wrong_status": wrong.status_code,
                "voted_status": voted.status_code,
                "voted_likes": voted.json().get("likes"),
                "public_likes": public_read.json()[0].get("likes"),
                "public_dislikes": public_read.json()[0].get("dislikes"),
                "removed_status": removed.status_code,
                "removed_likes": removed.json().get("likes"),
                "public_after_remove_likes": public_after_remove.json()[0].get("likes"),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["voted_status"], 200)
        self.assertEqual(result["voted_likes"][0]["voter"], "bob")
        self.assertEqual(result["public_likes"][0]["voter"], "bob")
        self.assertEqual(result["public_dislikes"], [])
        self.assertEqual(result["removed_status"], 200)
        self.assertEqual(result["removed_likes"], [])
        self.assertEqual(result["public_after_remove_likes"], [])

    def test_comment_delete_requires_original_author_bearer_identity(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            author_seeded = seed_comment_target(
                author="alice",
                proposal_owner="bob",
                content="delete by author",
            )
            author_comment_id = author_seeded["comment_id"]
            missing = client.delete(f"/comments/{author_comment_id}?user=alice")
            invalid = client.delete(
                f"/comments/{author_comment_id}?user=alice",
                headers=invalid_headers,
            )
            wrong = client.delete(
                f"/comments/{author_comment_id}?user=alice",
                headers=cara_headers,
            )
            matching_author = client.delete(
                f"/comments/{author_comment_id}?user=alice",
                headers=alice_headers,
            )

            owner_seeded = seed_comment_target(
                author="alice",
                proposal_owner="bob",
                content="delete by owner",
            )
            owner_comment_id = owner_seeded["comment_id"]
            matching_owner = client.delete(
                f"/comments/{owner_comment_id}?user=bob",
                headers=bob_headers,
            )
            owner_read = client.get(f"/comments?proposal_id={owner_seeded['proposal_id']}")
            author_payload = matching_author.json()
            owner_payload = matching_owner.json()
            result = {
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "matching_author_status": matching_author.status_code,
                "matching_author_keys": sorted(author_payload.keys()),
                "matching_author_deleted": author_payload.get("deleted"),
                "matching_author_tombstone": author_payload.get("tombstone"),
                "matching_owner_status": matching_owner.status_code,
                "matching_owner_detail": owner_payload.get("detail"),
                "matching_owner_deleted": owner_payload.get("deleted"),
                "matching_owner_tombstone": owner_payload.get("tombstone"),
                "owner_read_status": owner_read.status_code,
                "owner_read_count": len(owner_read.json()),
            }
            print("AUTH_BOUND_WRITE_ROUTES_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_auth_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["matching_author_status"], 200)
        self.assertEqual(
            set(result["matching_author_keys"]),
            {"deleted", "ok", "pruned_comment_ids", "tombstone"},
        )
        self.assertTrue(result["matching_author_deleted"])
        self.assertFalse(result["matching_author_tombstone"])
        self.assertEqual(result["matching_owner_status"], 403)
        self.assertIn("original comment author", result["matching_owner_detail"])
        self.assertIsNone(result["matching_owner_deleted"])
        self.assertIsNone(result["matching_owner_tombstone"])
        self.assertEqual(result["owner_read_status"], 200)
        self.assertEqual(result["owner_read_count"], 1)


if __name__ == "__main__":
    unittest.main()
