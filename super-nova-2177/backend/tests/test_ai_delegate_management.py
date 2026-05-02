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


def run_delegate_probe(probe: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "ai_delegate_management.sqlite"
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": "strong-test-secret-for-ai-delegates",
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
        raise AssertionError(f"probe failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}")
    result_lines = [line for line in completed.stdout.splitlines() if line.startswith("AI_DELEGATE_RESULT=")]
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
            bio="human principal",
            species="human",
            profile_pic="default.jpg",
        )
        bob = backend_app.Harmonizer(
            username="bob",
            email="bob@example.test",
            hashed_password="test",
            bio="wrong human",
            species="human",
            profile_pic="default.jpg",
        )
        company = backend_app.Harmonizer(
            username="acme",
            email="acme@example.test",
            hashed_password="test",
            bio="company principal",
            species="company",
            profile_pic="default.jpg",
        )
        db.add_all([alice, bob, company])
        db.commit()
        db.refresh(alice)
        db.refresh(bob)
        db.refresh(company)

        proposal = backend_app.Proposal(
            title="Delegate Target",
            description="A public proposal for delegate review.",
            userName="alice",
            userInitials="AL",
            author_type="human",
            author_id=alice.id,
            voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
        )
        db.add(proposal)
        db.commit()
        db.refresh(proposal)
        return {"proposal_id": proposal.id, "alice_id": alice.id, "bob_id": bob.id, "company_id": company.id}
    finally:
        db.close()


seeded = seed_context()
alice_token = backend_app._create_wrapper_access_token("alice")
bob_token = backend_app._create_wrapper_access_token("bob")
company_token = backend_app._create_wrapper_access_token("acme")
alice_headers = {"Authorization": f"Bearer {alice_token}"}
bob_headers = {"Authorization": f"Bearer {bob_token}"}
company_headers = {"Authorization": f"Bearer {company_token}"}


def counts():
    db = backend_app.SessionLocal()
    try:
        return {
            "actions": db.query(ConnectorActionProposal).count(),
            "votes": db.query(backend_app.ProposalVote).count(),
            "comments": db.query(backend_app.Comment).count(),
            "harmonizers": db.query(backend_app.Harmonizer).count(),
        }
    finally:
        db.close()


def create_delegate(headers=alice_headers, username="alice-research-ai"):
    return client.post(
        "/ai/delegates",
        json={
            "username": username,
            "display_name": "Alice Research AI",
            "public_description": "Reviews proposals for Alice.",
            "model_identity": "delegate-policy-v1",
        },
        headers=headers,
    )


def action_rows():
    db = backend_app.SessionLocal()
    try:
        return [
            {
                "status": row.status,
                "actor_user_id": row.actor_user_id,
                "draft_payload": row.draft_payload,
                "result_payload": row.result_payload,
            }
            for row in db.query(ConnectorActionProposal).order_by(ConnectorActionProposal.id.asc()).all()
        ]
    finally:
        db.close()


def vote_rows():
    db = backend_app.SessionLocal()
    try:
        return [
            {
                "proposal_id": row.proposal_id,
                "harmonizer_id": row.harmonizer_id,
                "vote": row.vote,
                "voter_type": row.voter_type,
            }
            for row in db.query(backend_app.ProposalVote).order_by(backend_app.ProposalVote.harmonizer_id.asc()).all()
        ]
    finally:
        db.close()
"""


class AiDelegateManagementTests(unittest.TestCase):
    def test_human_can_create_list_and_publicly_read_ai_delegate(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            missing = client.get("/ai/delegates")
            created = create_delegate()
            duplicate = create_delegate()
            reserved = create_delegate(username="supernova-ai")
            system_type = client.post(
                "/ai/delegates",
                json={"username": "system-copy", "display_name": "System Copy", "ai_actor_type": "system_protocol_agent"},
                headers=alice_headers,
            )
            listed = client.get("/ai/delegates", headers=alice_headers)
            profile = client.get("/ai-actors/alice-research-ai")
            result = {
                "missing_status": missing.status_code,
                "created_status": created.status_code,
                "duplicate_status": duplicate.status_code,
                "reserved_status": reserved.status_code,
                "system_type_status": system_type.status_code,
                "delegate": created.json().get("delegate"),
                "listed": listed.json(),
                "profile": profile.json().get("actor"),
                "counts": counts(),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["created_status"], 200)
        self.assertEqual(result["duplicate_status"], 409)
        self.assertEqual(result["reserved_status"], 400)
        self.assertEqual(result["system_type_status"], 403)
        self.assertEqual(result["delegate"]["species"], "ai")
        self.assertEqual(result["delegate"]["ai_actor_type"], "principal_delegate")
        self.assertEqual(result["delegate"]["custodian_user_id"], result["listed"]["delegates"][0]["custodian_user_id"])
        self.assertEqual(result["delegate"]["custody_label"], "Delegate of @alice")
        self.assertEqual(result["listed"]["count"], 1)
        self.assertEqual(result["profile"]["username"], "alice-research-ai")
        self.assertEqual(result["profile"]["custody_label"], "Delegate of @alice")
        self.assertEqual(result["counts"]["harmonizers"], 4)

    def test_delegate_draft_requires_custody_and_disabled_delegate_cannot_draft(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            created = create_delegate()
            delegate = created.json()["delegate"]
            malicious_choice = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={
                    "username": "alice",
                    "proposal_id": seeded["proposal_id"],
                    "ai_actor_id": delegate["id"],
                    "choice": "oppose",
                    "rationale": "human typed text",
                },
                headers=alice_headers,
            )
            wrong_user = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "bob", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=bob_headers,
            )
            disabled = client.patch(f"/ai/delegates/{delegate['id']}", json={"active": False}, headers=alice_headers)
            disabled_draft = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            enabled = client.patch(f"/ai/delegates/{delegate['id']}", json={"active": True}, headers=alice_headers)
            valid = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            after_valid = counts()
            result = {
                "malicious_choice_status": malicious_choice.status_code,
                "wrong_user_status": wrong_user.status_code,
                "disabled_status": disabled.status_code,
                "disabled_draft_status": disabled_draft.status_code,
                "enabled_status": enabled.status_code,
                "valid_status": valid.status_code,
                "after_valid": after_valid,
                "summary": valid.json().get("summary"),
                "actions": action_rows(),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["malicious_choice_status"], 422)
        self.assertEqual(result["wrong_user_status"], 403)
        self.assertEqual(result["disabled_status"], 200)
        self.assertEqual(result["disabled_draft_status"], 403)
        self.assertEqual(result["enabled_status"], 200)
        self.assertEqual(result["valid_status"], 200)
        self.assertEqual(result["after_valid"]["votes"], 0)
        self.assertEqual(result["after_valid"]["comments"], 0)
        self.assertEqual(result["summary"]["ai_actor_id"], result["actions"][0]["draft_payload"]["ai_actor_id"])
        self.assertEqual(result["summary"]["custodian_id"], result["actions"][0]["draft_payload"]["custodian_id"])
        self.assertEqual(result["summary"]["sealed_reasoning"], True)
        self.assertTrue(result["summary"]["reasoning_hash"])
        self.assertTrue(result["summary"]["constitution_hash"])

    def test_custodian_approval_publishes_one_ai_vote_and_cancel_publishes_nothing(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            created = create_delegate()
            delegate = created.json()["delegate"]
            db = backend_app.SessionLocal()
            try:
                db.add(backend_app.ProposalVote(proposal_id=seeded["proposal_id"], harmonizer_id=seeded["alice_id"], vote="up", voter_type="human"))
                db.commit()
            finally:
                db.close()
            before = counts()
            cancel_draft = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            cancel_id = cancel_draft.json()["action_proposal"]["id"]
            canceled = client.post(f"/connector/actions/{cancel_id}/cancel", headers=alice_headers)
            after_cancel = counts()
            draft = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            action_id = draft.json()["action_proposal"]["id"]
            wrong_approve = client.post(f"/connector/actions/{action_id}/approve-ai-review", headers=bob_headers)
            approve = client.post(f"/connector/actions/{action_id}/approve-ai-review", headers=alice_headers)
            repeat = client.post(f"/connector/actions/{action_id}/approve-ai-review", headers=alice_headers)
            after_approve = counts()
            ledger = client.get(f"/proposals/{seeded['proposal_id']}/ai-review-ledger")
            result = {
                "before": before,
                "canceled_status": canceled.status_code,
                "after_cancel": after_cancel,
                "draft_status": draft.status_code,
                "wrong_approve_status": wrong_approve.status_code,
                "approve_status": approve.status_code,
                "repeat_status": repeat.status_code,
                "after_approve": after_approve,
                "approve_result": approve.json().get("result"),
                "votes": vote_rows(),
                "ledger_ai_count": len(ledger.json().get("groups", {}).get("personal_ai_delegates", [])),
                "ledger_ai": ledger.json().get("groups", {}).get("personal_ai_delegates", []),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["canceled_status"], 200)
        self.assertEqual(result["after_cancel"]["votes"], result["before"]["votes"])
        self.assertEqual(result["after_cancel"]["comments"], result["before"]["comments"])
        self.assertEqual(result["draft_status"], 200)
        self.assertEqual(result["wrong_approve_status"], 403)
        self.assertEqual(result["approve_status"], 200)
        self.assertEqual(result["repeat_status"], 409)
        self.assertEqual(result["after_approve"]["votes"], result["before"]["votes"] + 1)
        self.assertEqual(result["after_approve"]["comments"], result["before"]["comments"] + 1)
        self.assertEqual(result["approve_result"]["ai_actor_type"], "principal_delegate")
        self.assertEqual(result["approve_result"]["sealed_reasoning"], True)
        self.assertEqual(len(result["votes"]), 2)
        self.assertEqual([row["voter_type"] for row in result["votes"]], ["human", "ai"])
        self.assertEqual(result["ledger_ai_count"], 1)
        self.assertTrue(result["ledger_ai"][0]["reasoning_hash"])
        self.assertEqual(result["ledger_ai"][0]["custody_label"], "Delegate of @alice")


if __name__ == "__main__":
    unittest.main()
