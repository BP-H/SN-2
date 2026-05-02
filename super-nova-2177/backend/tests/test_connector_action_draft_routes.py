import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_draft_probe(probe: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "connector_action_draft_routes.sqlite"
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": "strong-test-secret-for-connector-action-drafts",
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
        if line.startswith("CONNECTOR_ACTION_DRAFT_RESULT=")
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

project_root = Path.cwd()
backend_dir = project_root / "backend"
for path in (project_root, backend_dir):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

import backend.app as backend_app
from db_models import Base, ConnectorActionProposal, Notification, ProposalCollab

backend_app.FOLLOWS_STORE_PATH = Path(os.environ["FOLLOWS_STORE_PATH"])
client = TestClient(backend_app.app)


def current_bind():
    session = backend_app.SessionLocal()
    try:
        return session.get_bind()
    finally:
        session.close()


Base.metadata.create_all(bind=current_bind())


def seed_context():
    db = backend_app.SessionLocal()
    try:
        alice = backend_app.Harmonizer(
            username="alice",
            email="alice@example.test",
            hashed_password="test",
            bio="author",
            species="human",
            profile_pic="default.jpg",
        )
        bob = backend_app.Harmonizer(
            username="bob",
            email="bob@example.test",
            hashed_password="test",
            bio="collaborator",
            species="ai",
            profile_pic="default.jpg",
        )
        cara = backend_app.Harmonizer(
            username="cara",
            email="cara@example.test",
            hashed_password="test",
            bio="wrong user",
            species="company",
            profile_pic="default.jpg",
        )
        db.add_all([alice, bob, cara])
        db.commit()
        db.refresh(alice)
        db.refresh(bob)

        node = backend_app.VibeNode(name="connector-action-draft-node", author_id=alice.id)
        proposal = backend_app.Proposal(
            title="Connector Draft Target",
            description="Target proposal for draft action tests.",
            userName="alice",
            userInitials="AL",
            author_type="human",
            author_id=alice.id,
            voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        )
        db.add_all([node, proposal])
        db.commit()
        db.refresh(proposal)
        return {"proposal_id": proposal.id}
    finally:
        db.close()


seeded = seed_context()
alice_token = backend_app._create_wrapper_access_token("alice")
bob_token = backend_app._create_wrapper_access_token("bob")
alice_headers = {"Authorization": f"Bearer {alice_token}"}
bob_headers = {"Authorization": f"Bearer {bob_token}"}
invalid_headers = {"Authorization": "Bearer not-a-valid-token"}


def counts():
    db = backend_app.SessionLocal()
    try:
        return {
            "actions": db.query(ConnectorActionProposal).count(),
            "votes": db.query(backend_app.ProposalVote).count(),
            "comments": db.query(backend_app.Comment).count(),
            "proposals": db.query(backend_app.Proposal).count(),
            "collabs": db.query(ProposalCollab).count(),
            "notifications": db.query(Notification).count(),
        }
    finally:
        db.close()


def action_rows():
    db = backend_app.SessionLocal()
    try:
        rows = db.query(ConnectorActionProposal).order_by(ConnectorActionProposal.id.asc()).all()
        return [
            {
                "id": row.id,
                "action_type": row.action_type,
                "actor_user_id": row.actor_user_id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "status": row.status,
                "draft_payload": row.draft_payload,
            }
            for row in rows
        ]
    finally:
        db.close()


def connector_action_routes():
    return sorted(
        route.path
        for route in backend_app.app.routes
        if route.path.startswith("/connector/actions")
    )
"""


class ConnectorActionDraftRouteTests(unittest.TestCase):
    def test_draft_vote_requires_auth_and_does_not_execute_vote(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            before = counts()
            body = {"username": "alice", "proposal_id": seeded["proposal_id"], "choice": "support"}
            missing = client.post("/connector/actions/draft-vote", json=body)
            invalid = client.post("/connector/actions/draft-vote", json=body, headers=invalid_headers)
            wrong = client.post("/connector/actions/draft-vote", json=body, headers=bob_headers)
            invalid_choice = client.post(
                "/connector/actions/draft-vote",
                json={**body, "choice": "maybe"},
                headers=alice_headers,
            )
            unknown_proposal = client.post(
                "/connector/actions/draft-vote",
                json={**body, "proposal_id": 999999},
                headers=alice_headers,
            )
            matching = client.post("/connector/actions/draft-vote", json=body, headers=alice_headers)
            after = counts()
            payload = matching.json()
            result = {
                "before": before,
                "after": after,
                "missing_status": missing.status_code,
                "invalid_status": invalid.status_code,
                "wrong_status": wrong.status_code,
                "invalid_choice_status": invalid_choice.status_code,
                "unknown_proposal_status": unknown_proposal.status_code,
                "matching_status": matching.status_code,
                "response_keys": sorted(payload.keys()),
                "executed": payload.get("executed"),
                "action_type": payload.get("action_proposal", {}).get("action_type"),
                "status": payload.get("action_proposal", {}).get("status"),
                "target_id": payload.get("action_proposal", {}).get("target_id"),
                "summary": payload.get("summary"),
                "actions": action_rows(),
            }
            print("CONNECTOR_ACTION_DRAFT_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_draft_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["invalid_status"], 401)
        self.assertEqual(result["wrong_status"], 403)
        self.assertEqual(result["invalid_choice_status"], 400)
        self.assertEqual(result["unknown_proposal_status"], 404)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(
            set(result["response_keys"]),
            {"action_proposal", "executed", "mode", "ok", "safety", "summary"},
        )
        self.assertFalse(result["executed"])
        self.assertEqual(result["action_type"], "draft_vote")
        self.assertEqual(result["status"], "draft")
        self.assertEqual(result["summary"]["intended_choice"], "support")
        self.assertEqual(result["summary"]["normalized_vote"], "up")
        self.assertEqual(result["after"]["actions"], result["before"]["actions"] + 1)
        self.assertEqual(result["after"]["votes"], result["before"]["votes"])
        self.assertEqual(result["after"]["comments"], result["before"]["comments"])
        self.assertEqual(result["after"]["proposals"], result["before"]["proposals"])
        self.assertEqual(result["after"]["collabs"], result["before"]["collabs"])
        self.assertEqual(result["after"]["notifications"], result["before"]["notifications"])
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["action_type"], "draft_vote")
        self.assertEqual(result["actions"][0]["status"], "draft")

    def test_draft_comment_proposal_and_collab_create_only_action_records(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            before = counts()
            comment = client.post(
                "/connector/actions/draft-comment",
                json={
                    "username": "alice",
                    "proposal_id": seeded["proposal_id"],
                    "body": "Draft comment mentioning @bob but not notifying.",
                },
                headers=alice_headers,
            )
            proposal = client.post(
                "/connector/actions/draft-proposal",
                json={
                    "author": "alice",
                    "title": "Draft proposal only",
                    "body": "Draft body @bob with no real proposal row.",
                },
                headers=alice_headers,
            )
            collab = client.post(
                "/connector/actions/draft-collab-request",
                json={
                    "author": "alice",
                    "proposal_id": seeded["proposal_id"],
                    "collaborator_username": "bob",
                },
                headers=alice_headers,
            )
            wrong_collab_author = client.post(
                "/connector/actions/draft-collab-request",
                json={
                    "author": "bob",
                    "proposal_id": seeded["proposal_id"],
                    "collaborator_username": "alice",
                },
                headers=bob_headers,
            )
            missing_collaborator = client.post(
                "/connector/actions/draft-collab-request",
                json={
                    "author": "alice",
                    "proposal_id": seeded["proposal_id"],
                    "collaborator_username": "ghost-user",
                },
                headers=alice_headers,
            )
            after = counts()
            result = {
                "before": before,
                "after": after,
                "comment_status": comment.status_code,
                "proposal_status": proposal.status_code,
                "collab_status": collab.status_code,
                "wrong_collab_author_status": wrong_collab_author.status_code,
                "missing_collaborator_status": missing_collaborator.status_code,
                "comment_summary": comment.json().get("summary"),
                "proposal_summary": proposal.json().get("summary"),
                "collab_summary": collab.json().get("summary"),
                "actions": action_rows(),
            }
            print("CONNECTOR_ACTION_DRAFT_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_draft_probe(probe)

        self.assertEqual(result["comment_status"], 200)
        self.assertEqual(result["proposal_status"], 200)
        self.assertEqual(result["collab_status"], 200)
        self.assertEqual(result["wrong_collab_author_status"], 403)
        self.assertEqual(result["missing_collaborator_status"], 404)
        self.assertEqual(result["after"]["actions"], result["before"]["actions"] + 3)
        self.assertEqual(result["after"]["votes"], result["before"]["votes"])
        self.assertEqual(result["after"]["comments"], result["before"]["comments"])
        self.assertEqual(result["after"]["proposals"], result["before"]["proposals"])
        self.assertEqual(result["after"]["collabs"], result["before"]["collabs"])
        self.assertEqual(result["after"]["notifications"], result["before"]["notifications"])
        self.assertEqual(
            [row["action_type"] for row in result["actions"]],
            ["draft_comment", "draft_proposal", "draft_collab_request"],
        )
        self.assertTrue(all(row["status"] == "draft" for row in result["actions"]))
        self.assertEqual(result["comment_summary"]["action"], "draft_comment")
        self.assertEqual(result["proposal_summary"]["action"], "draft_proposal")
        self.assertEqual(result["collab_summary"]["collaborator_username"], "bob")

    def test_connector_action_routes_include_inbox_cancel_drafts_and_vote_approval_only(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            routes = connector_action_routes()
            result = {
                "routes": routes,
                "execution_routes": [
                    path for path in routes if "approve" in path or "execute" in path
                ],
            }
            print("CONNECTOR_ACTION_DRAFT_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_draft_probe(probe)

        self.assertEqual(
            result["routes"],
            [
                "/connector/actions",
                "/connector/actions/draft-ai-delegate-review",
                "/connector/actions/draft-ai-review",
                "/connector/actions/draft-collab-request",
                "/connector/actions/draft-comment",
                "/connector/actions/draft-proposal",
                "/connector/actions/draft-vote",
                "/connector/actions/{action_id}/approve-ai-review",
                "/connector/actions/{action_id}/approve-vote",
                "/connector/actions/{action_id}/cancel",
            ],
        )
        self.assertEqual(
            result["execution_routes"],
            [
                "/connector/actions/{action_id}/approve-ai-review",
                "/connector/actions/{action_id}/approve-vote",
            ],
        )


if __name__ == "__main__":
    unittest.main()
