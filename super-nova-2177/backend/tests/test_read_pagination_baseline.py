import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_probe(probe: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "read_pagination_baseline.sqlite"
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": "strong-test-secret-for-read-pagination-baseline",
                "SUPERNOVA_ENV": "development",
                "APP_ENV": "development",
                "ENV": "development",
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
        if line.startswith("READ_PAGINATION_BASELINE_RESULT=")
    ]
    if not result_lines:
        raise AssertionError(f"probe result missing\nstdout:\n{completed.stdout}")
    return json.loads(result_lines[-1].split("=", 1)[1])


PROBE_PREAMBLE = """
import datetime
import json
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

import backend.app as backend_app
from db_models import Base

client = TestClient(backend_app.app)


def current_bind():
    session = backend_app.SessionLocal()
    try:
        return session.get_bind()
    finally:
        session.close()


Base.metadata.create_all(bind=current_bind())


def seed_social_graph():
    db = backend_app.SessionLocal()
    try:
        alice = backend_app.Harmonizer(
            username="alice",
            email="alice@example.test",
            hashed_password="test",
            species="human",
            profile_pic="",
        )
        bob = backend_app.Harmonizer(
            username="bob",
            email="bob@example.test",
            hashed_password="test",
            species="ai",
            profile_pic="",
        )
        cara = backend_app.Harmonizer(
            username="cara",
            email="cara@example.test",
            hashed_password="test",
            species="company",
            profile_pic="",
        )
        db.add_all([alice, bob, cara])
        db.commit()
        for item in (alice, bob, cara):
            db.refresh(item)

        node = backend_app.VibeNode(name="baseline-node", author_id=alice.id)
        proposal = backend_app.Proposal(
            title="Pagination baseline proposal",
            description="Pins current read route behavior.",
            userName="alice",
            userInitials="AL",
            author_type="human",
            author_id=alice.id,
            voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        )
        db.add_all([node, proposal])
        db.commit()
        db.refresh(node)
        db.refresh(proposal)

        comments = [
            backend_app.Comment(
                content="first baseline comment",
                author_id=alice.id,
                vibenode_id=node.id,
                proposal_id=proposal.id,
                created_at=datetime.datetime(2026, 1, 1, 12, 0, 0),
            ),
            backend_app.Comment(
                content="second baseline comment",
                author_id=bob.id,
                vibenode_id=node.id,
                proposal_id=proposal.id,
                parent_comment_id=None,
                created_at=datetime.datetime(2026, 1, 1, 12, 1, 0),
            ),
            backend_app.Comment(
                content="third baseline comment",
                author_id=cara.id,
                vibenode_id=node.id,
                proposal_id=proposal.id,
                created_at=datetime.datetime(2026, 1, 1, 12, 2, 0),
            ),
        ]
        votes = [
            backend_app.ProposalVote(
                proposal_id=proposal.id,
                harmonizer_id=alice.id,
                vote="up",
                voter_type="human",
            ),
            backend_app.ProposalVote(
                proposal_id=proposal.id,
                harmonizer_id=bob.id,
                vote="down",
                voter_type="ai",
            ),
        ]
        db.add_all(comments + votes)
        db.commit()
        return {
            "proposal_id": proposal.id,
            "comment_ids": [comment.id for comment in comments],
        }
    finally:
        db.close()
"""


class ReadPaginationBaselineTests(unittest.TestCase):
    def test_comments_without_pagination_params_return_full_current_shape(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_social_graph()
            response = client.get(f"/comments?proposal_id={seeded['proposal_id']}")
            payload = response.json()
            result = {
                "status_code": response.status_code,
                "count": len(payload),
                "ids": [item.get("id") for item in payload],
                "comments": [item.get("comment") for item in payload],
                "shape_keys": sorted(payload[0].keys()) if payload else [],
            }
            print("READ_PAGINATION_BASELINE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["comments"], [
            "first baseline comment",
            "second baseline comment",
            "third baseline comment",
        ])
        self.assertEqual(result["ids"], sorted(result["ids"]))
        self.assertEqual(
            set(result["shape_keys"]),
            {
                "comment",
                "created_at",
                "deleted",
                "id",
                "likes",
                "dislikes",
                "parent_comment_id",
                "proposal_id",
                "species",
                "user",
                "user_img",
            },
        )

    def test_messages_peer_thread_without_pagination_returns_full_thread_only(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seed_social_graph()
            db = backend_app.SessionLocal()
            try:
                backend_app._ensure_direct_messages_table(db)
                alice_bob = backend_app._conversation_id("alice", "bob")
                alice_cara = backend_app._conversation_id("alice", "cara")
                rows = [
                    {
                        "id": "msg-1",
                        "conversation_id": alice_bob,
                        "sender": "alice",
                        "recipient": "bob",
                        "body": "one",
                        "created_at": "2026-01-01T12:00:00",
                    },
                    {
                        "id": "msg-2",
                        "conversation_id": alice_bob,
                        "sender": "bob",
                        "recipient": "alice",
                        "body": "two",
                        "created_at": "2026-01-01T12:01:00",
                    },
                    {
                        "id": "msg-3",
                        "conversation_id": alice_bob,
                        "sender": "alice",
                        "recipient": "bob",
                        "body": "three",
                        "created_at": "2026-01-01T12:02:00",
                    },
                    {
                        "id": "msg-other",
                        "conversation_id": alice_cara,
                        "sender": "alice",
                        "recipient": "cara",
                        "body": "other peer",
                        "created_at": "2026-01-01T12:03:00",
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

            alice_token = backend_app._create_wrapper_access_token("alice")
            response = client.get(
                "/messages?user=alice&peer=bob",
                headers={"Authorization": f"Bearer {alice_token}"},
            )
            payload = response.json()
            messages = payload.get("messages", [])
            result = {
                "status_code": response.status_code,
                "peer": payload.get("peer"),
                "ids": [item.get("id") for item in messages],
                "bodies": [item.get("body") for item in messages],
                "conversation_ids": sorted({item.get("conversation_id") for item in messages}),
            }
            print("READ_PAGINATION_BASELINE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["peer"], "bob")
        self.assertEqual(result["ids"], ["msg-1", "msg-2", "msg-3"])
        self.assertEqual(result["bodies"], ["one", "two", "three"])
        self.assertEqual(len(result["conversation_ids"]), 1)

    def test_proposals_without_embedded_caps_keep_full_embedded_shape(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_social_graph()
            response = client.get("/proposals?filter=latest&author=alice&limit=10")
            payload = response.json()
            proposal = payload[0]
            result = {
                "status_code": response.status_code,
                "count": len(payload),
                "proposal_id": proposal.get("id"),
                "comment_count": len(proposal.get("comments", [])),
                "like_count": len(proposal.get("likes", [])),
                "dislike_count": len(proposal.get("dislikes", [])),
                "comment_texts": [item.get("comment") for item in proposal.get("comments", [])],
                "proposal_keys": sorted(proposal.keys()),
                "comment_shape_keys": sorted(proposal["comments"][0].keys()),
            }
            print("READ_PAGINATION_BASELINE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["comment_count"], 3)
        self.assertEqual(result["like_count"], 1)
        self.assertEqual(result["dislike_count"], 1)
        self.assertEqual(result["comment_texts"], [
            "first baseline comment",
            "second baseline comment",
            "third baseline comment",
        ])
        self.assertIn("comments", result["proposal_keys"])
        self.assertIn("likes", result["proposal_keys"])
        self.assertIn("dislikes", result["proposal_keys"])
        self.assertEqual(
            set(result["comment_shape_keys"]),
            {
                "comment",
                "created_at",
                "deleted",
                "id",
                "likes",
                "dislikes",
                "parent_comment_id",
                "proposal_id",
                "species",
                "user",
                "user_img",
            },
        )


if __name__ == "__main__":
    unittest.main()
