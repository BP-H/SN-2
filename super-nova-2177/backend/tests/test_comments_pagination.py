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
        db_path = Path(tmpdir) / "comments_pagination.sqlite"
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": "strong-test-secret-for-comments-pagination",
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
        if line.startswith("COMMENTS_PAGINATION_RESULT=")
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


def seed_comments(count=4):
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
        db.add_all([alice, bob])
        db.commit()
        db.refresh(alice)
        db.refresh(bob)

        node = backend_app.VibeNode(name="comments-pagination-node", author_id=alice.id)
        primary = backend_app.Proposal(
            title="Primary comments pagination proposal",
            description="Primary proposal for comments pagination tests.",
            userName="alice",
            userInitials="AL",
            author_type="human",
            author_id=alice.id,
            voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        )
        other = backend_app.Proposal(
            title="Other proposal",
            description="Should not leak into primary comment reads.",
            userName="bob",
            userInitials="BO",
            author_type="ai",
            author_id=bob.id,
            voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        )
        db.add_all([node, primary, other])
        db.commit()
        db.refresh(node)
        db.refresh(primary)
        db.refresh(other)

        comments = []
        for index in range(count):
            comments.append(
                backend_app.Comment(
                    content=f"primary comment {index:03d}",
                    author_id=alice.id if index % 2 == 0 else bob.id,
                    vibenode_id=node.id,
                    proposal_id=primary.id,
                    created_at=datetime.datetime(2026, 1, 1, 12, 0, 0)
                    + datetime.timedelta(minutes=index),
                )
            )
        comments.append(
            backend_app.Comment(
                content="other proposal comment",
                author_id=bob.id,
                vibenode_id=node.id,
                proposal_id=other.id,
                created_at=datetime.datetime(2026, 1, 2, 12, 0, 0),
            )
        )
        db.add_all(comments)
        db.commit()
        return {
            "primary_id": primary.id,
            "other_id": other.id,
            "primary_count": count,
        }
    finally:
        db.close()
"""


class CommentsPaginationTests(unittest.TestCase):
    def test_comments_without_pagination_params_keep_full_current_shape(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comments(count=4)
            response = client.get(f"/comments?proposal_id={seeded['primary_id']}")
            payload = response.json()
            result = {
                "status_code": response.status_code,
                "count": len(payload),
                "comments": [item.get("comment") for item in payload],
                "ids": [item.get("id") for item in payload],
                "shape_keys": sorted(payload[0].keys()) if payload else [],
            }
            print("COMMENTS_PAGINATION_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["count"], 4)
        self.assertEqual(
            result["comments"],
            [
                "primary comment 000",
                "primary comment 001",
                "primary comment 002",
                "primary comment 003",
            ],
        )
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

    def test_comments_limit_returns_first_stable_slice_without_leaks(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comments(count=4)
            response = client.get(f"/comments?proposal_id={seeded['primary_id']}&limit=2")
            payload = response.json()
            result = {
                "status_code": response.status_code,
                "count": len(payload),
                "comments": [item.get("comment") for item in payload],
                "proposal_ids": sorted({item.get("proposal_id") for item in payload}),
            }
            print("COMMENTS_PAGINATION_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["comments"], ["primary comment 000", "primary comment 001"])
        self.assertEqual(len(result["proposal_ids"]), 1)

    def test_comments_limit_and_offset_return_expected_stable_slice(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comments(count=4)
            response = client.get(
                f"/comments?proposal_id={seeded['primary_id']}&limit=2&offset=1"
            )
            payload = response.json()
            result = {
                "status_code": response.status_code,
                "count": len(payload),
                "comments": [item.get("comment") for item in payload],
            }
            print("COMMENTS_PAGINATION_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["comments"], ["primary comment 001", "primary comment 002"])

    def test_comments_excessive_limit_is_clamped(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comments(count=505)
            response = client.get(
                f"/comments?proposal_id={seeded['primary_id']}&limit=9999"
            )
            payload = response.json()
            result = {
                "status_code": response.status_code,
                "count": len(payload),
                "first": payload[0].get("comment") if payload else "",
                "last": payload[-1].get("comment") if payload else "",
            }
            print("COMMENTS_PAGINATION_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["count"], 500)
        self.assertEqual(result["first"], "primary comment 000")
        self.assertEqual(result["last"], "primary comment 499")

    def test_comments_invalid_limit_rejects_and_negative_offset_normalizes(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            seeded = seed_comments(count=4)
            invalid_limit = client.get(
                f"/comments?proposal_id={seeded['primary_id']}&limit=not-an-int"
            )
            negative_offset = client.get(
                f"/comments?proposal_id={seeded['primary_id']}&limit=2&offset=-10"
            )
            payload = negative_offset.json()
            result = {
                "invalid_limit_status": invalid_limit.status_code,
                "negative_offset_status": negative_offset.status_code,
                "negative_offset_comments": [item.get("comment") for item in payload],
            }
            print("COMMENTS_PAGINATION_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_probe(probe)

        self.assertEqual(result["invalid_limit_status"], 422)
        self.assertEqual(result["negative_offset_status"], 200)
        self.assertEqual(
            result["negative_offset_comments"],
            ["primary comment 000", "primary comment 001"],
        )


if __name__ == "__main__":
    unittest.main()
