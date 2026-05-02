import datetime
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_ai_actor_probe(probe: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "ai_actor_system_review.sqlite"
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": "strong-test-secret-for-ai-actors",
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
        if line.startswith("AI_ACTOR_SYSTEM_REVIEW_RESULT=")
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
from db_models import Base, ConnectorActionProposal

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
            bio="human author",
            species="human",
            profile_pic="default.jpg",
        )
        company = backend_app.Harmonizer(
            username="acme",
            email="acme@example.test",
            hashed_password="test",
            bio="company voter",
            species="company",
            profile_pic="default.jpg",
        )
        bot = backend_app.Harmonizer(
            username="alice-ai",
            email="alice-ai@example.test",
            hashed_password="test",
            bio="AI delegate",
            species="ai",
            profile_pic="default.jpg",
        )
        db.add_all([alice, company, bot])
        db.commit()
        db.refresh(alice)
        db.refresh(company)
        db.refresh(bot)

        proposal = backend_app.Proposal(
            title="Protocol Review Target",
            description="A public-interest proposal with manual ratification.",
            userName="alice",
            userInitials="AL",
            author_type="human",
            author_id=alice.id,
            voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)

        db.add_all(
            [
                backend_app.ProposalVote(proposal_id=proposal.id, harmonizer_id=alice.id, vote="up", voter_type="human"),
                backend_app.ProposalVote(proposal_id=proposal.id, harmonizer_id=company.id, vote="down", voter_type="company"),
            ]
        )
        db.commit()
        return {"proposal_id": proposal.id, "bot_id": bot.id}
    finally:
        db.close()


seeded = seed_context()
alice_token = backend_app._create_wrapper_access_token("alice")
bot_token = backend_app._create_wrapper_access_token("alice-ai")
alice_headers = {"Authorization": f"Bearer {alice_token}"}
bot_headers = {"Authorization": f"Bearer {bot_token}"}


def counts():
    db = backend_app.SessionLocal()
    try:
        return {
            "actions": db.query(ConnectorActionProposal).count(),
            "votes": db.query(backend_app.ProposalVote).count(),
            "comments": db.query(backend_app.Comment).count(),
        }
    finally:
        db.close()


def action_rows():
    db = backend_app.SessionLocal()
    try:
        return [
            {
                "status": row.status,
                "action_type": row.action_type,
                "draft_payload": row.draft_payload,
                "result_payload": row.result_payload,
            }
            for row in db.query(ConnectorActionProposal).order_by(ConnectorActionProposal.id.asc()).all()
        ]
    finally:
        db.close()
"""


class AiActorSystemReviewTests(unittest.TestCase):
    def test_system_ai_profile_and_review_are_public_read_only(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            db = backend_app.SessionLocal()
            try:
                db.add(
                    backend_app.ProposalVote(
                        proposal_id=seeded["proposal_id"],
                        harmonizer_id=seeded["bot_id"],
                        vote="up",
                        voter_type="ai",
                    )
                )
                db.commit()
            finally:
                db.close()
            before = counts()
            actor = client.get("/ai-actors/supernova-ai")
            review = client.get(f"/proposals/{seeded['proposal_id']}/system-ai-review")
            ledger = client.get(f"/proposals/{seeded['proposal_id']}/ai-review-ledger")
            after = counts()
            result = {
                "before": before,
                "after": after,
                "actor_status": actor.status_code,
                "review_status": review.status_code,
                "ledger_status": ledger.status_code,
                "actor": actor.json().get("actor"),
                "review": review.json().get("review"),
                "ledger_groups": {key: len(value) for key, value in ledger.json().get("groups", {}).items()},
                "safety": review.json().get("safety"),
            }
            print("AI_ACTOR_SYSTEM_REVIEW_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_ai_actor_probe(probe)

        self.assertEqual(result["actor_status"], 200)
        self.assertEqual(result["review_status"], 200)
        self.assertEqual(result["ledger_status"], 200)
        self.assertEqual(result["actor"]["species"], "ai")
        self.assertEqual(result["actor"]["ai_actor_type"], "system_protocol_agent")
        self.assertEqual(result["actor"]["custody_label"], "Chartered by SuperNova Protocol")
        self.assertEqual(result["review"]["species"], "ai")
        self.assertEqual(result["review"]["ai_actor_type"], "system_protocol_agent")
        self.assertEqual(result["review"]["approval_status"], "published_advisory")
        self.assertTrue(result["review"]["reasoning_hash"])
        self.assertTrue(result["review"]["constitution_hash"])
        self.assertEqual(result["safety"]["no_vote_created"], True)
        self.assertEqual(result["safety"]["no_comment_created"], True)
        self.assertEqual(result["after"], result["before"])
        self.assertEqual(result["ledger_groups"]["humans"], 1)
        self.assertEqual(result["ledger_groups"]["organizations"], 1)
        self.assertEqual(result["ledger_groups"]["personal_ai_delegates"], 1)
        self.assertEqual(result["ledger_groups"]["system_ai"], 1)

    def test_locked_delegate_review_draft_generates_reasoning_server_side(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            before = counts()
            missing = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice-ai", "proposal_id": seeded["proposal_id"]},
            )
            wrong_user = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice-ai", "proposal_id": seeded["proposal_id"]},
                headers=alice_headers,
            )
            matching = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice-ai", "proposal_id": seeded["proposal_id"], "confidence": 0.77},
                headers=bot_headers,
            )
            after_draft = counts()
            action_id = matching.json()["action_proposal"]["id"]
            approve = client.post(f"/connector/actions/{action_id}/approve-ai-review", headers=bot_headers)
            after_approve = counts()
            result = {
                "before": before,
                "missing_status": missing.status_code,
                "wrong_user_status": wrong_user.status_code,
                "matching_status": matching.status_code,
                "approve_status": approve.status_code,
                "after_draft": after_draft,
                "after_approve": after_approve,
                "draft_summary": matching.json().get("summary"),
                "approve_result": approve.json().get("result"),
                "actions": action_rows(),
            }
            print("AI_ACTOR_SYSTEM_REVIEW_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_ai_actor_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["wrong_user_status"], 403)
        self.assertEqual(result["matching_status"], 200)
        self.assertEqual(result["approve_status"], 200)
        self.assertEqual(result["after_draft"]["votes"], result["before"]["votes"])
        self.assertEqual(result["after_draft"]["comments"], result["before"]["comments"])
        self.assertEqual(result["after_approve"]["votes"], result["before"]["votes"] + 1)
        self.assertEqual(result["after_approve"]["comments"], result["before"]["comments"] + 1)
        self.assertEqual(result["draft_summary"]["ai_actor_type"], "principal_delegate")
        self.assertEqual(result["draft_summary"]["sealed_reasoning"], True)
        self.assertEqual(result["draft_summary"]["reasoning_source"], "locked_server_charter")
        self.assertTrue(result["draft_summary"]["reasoning_hash"])
        self.assertEqual(result["approve_result"]["sealed_reasoning"], True)
        self.assertEqual(result["approve_result"]["reasoning_hash"], result["draft_summary"]["reasoning_hash"])


if __name__ == "__main__":
    unittest.main()
