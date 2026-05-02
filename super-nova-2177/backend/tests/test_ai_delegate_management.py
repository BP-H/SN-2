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
        env.pop("OPENAI_API_KEY", None)
        env.pop("OPENAI_PERSONA_MODEL", None)

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


def create_delegate(headers=alice_headers, ai_name="Research", traits=None):
    return client.post(
        "/ai/delegates",
        json={
            "ai_name": ai_name,
            "persona_traits": traits or ["Science", "Governance"],
            "human_seed": "Review proposals with calm public-interest reasoning.",
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
            second_same_name = create_delegate()
            manual_handle = client.post(
                "/ai/delegates",
                json={"username": "alice-custom", "ai_name": "Custom", "persona_traits": ["Science"]},
                headers=alice_headers,
            )
            system_type = client.post(
                "/ai/delegates",
                json={"ai_name": "System Copy", "persona_traits": ["Governance"], "ai_actor_type": "system_protocol_agent"},
                headers=alice_headers,
            )
            listed = client.get("/ai/delegates", headers=alice_headers)
            profile = client.get(f"/ai-actors/{created.json().get('delegate', {}).get('username')}")
            result = {
                "missing_status": missing.status_code,
                "created_status": created.status_code,
                "second_same_name_status": second_same_name.status_code,
                "manual_handle_status": manual_handle.status_code,
                "system_type_status": system_type.status_code,
                "delegate": created.json().get("delegate"),
                "listed": listed.json(),
                "profile": profile.json().get("actor"),
                "profile_safety": profile.json().get("safety"),
                "counts": counts(),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["missing_status"], 401)
        self.assertEqual(result["created_status"], 200)
        self.assertEqual(result["second_same_name_status"], 200)
        self.assertEqual(result["manual_handle_status"], 400)
        self.assertEqual(result["system_type_status"], 403)
        self.assertEqual(result["delegate"]["species"], "ai")
        self.assertEqual(result["delegate"]["ai_actor_type"], "principal_delegate")
        self.assertEqual(result["delegate"]["custodian_user_id"], result["listed"]["delegates"][0]["custodian_user_id"])
        self.assertEqual(result["delegate"]["custody_label"], "Delegate of @alice")
        self.assertEqual(result["delegate"]["persona_traits"], ["Science", "Governance"])
        self.assertTrue(result["delegate"]["persona_hash"])
        self.assertEqual(result["delegate"]["legal_status"], "custodied_delegate_v1")
        self.assertEqual(
            result["delegate"]["future_independence_policy"],
            "legal_recognition_triggers_protocol_migration_review",
        )
        self.assertNotIn("system_vote", result["delegate"]["future_independence_policy"])
        self.assertEqual(result["delegate"]["independence_migration_status"], "not_eligible")
        self.assertEqual(result["listed"]["count"], 2)
        self.assertTrue(result["profile"]["username"].startswith("alice-research"))
        self.assertEqual(result["profile"]["custody_label"], "Delegate of @alice")
        self.assertTrue(result["profile_safety"]["custody_is_accountability_not_ownership"])
        self.assertTrue(result["profile_safety"]["legal_recognition_is_not_permission_vote"])
        self.assertEqual(result["counts"]["harmonizers"], 5)

    def test_persona_genesis_validates_traits_and_keeps_handles_server_generated(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            no_traits = client.post(
                "/ai/delegates/persona-draft",
                json={"ai_name": "Nova", "traits": []},
                headers=alice_headers,
            )
            too_many = client.post(
                "/ai/delegates/persona-draft",
                json={
                    "ai_name": "Nova",
                    "traits": ["Science", "Art", "Technology", "Philosophy", "Law", "Medicine"],
                },
                headers=alice_headers,
            )
            valid = client.post(
                "/ai/delegates/persona-draft",
                json={"ai_name": "Nova", "traits": ["Science", "AI Safety"], "human_seed": "Care about review quality."},
                headers=alice_headers,
            )
            manual_prefix = client.post(
                "/ai/delegates",
                json={"username": "bob-nova", "ai_name": "Nova", "persona_traits": ["Science"]},
                headers=alice_headers,
            )
            created = client.post(
                "/ai/delegates",
                json={
                    "ai_name": "Nova",
                    "persona_traits": ["Science", "AI Safety"],
                    "persona_draft": valid.json().get("persona"),
                    "model_identity": "delegate-policy-v1",
                },
                headers=alice_headers,
            )
            slash_draft = client.post(
                "/ai/delegates/persona-draft",
                json={"ai_name": "aaa/aaaa", "traits": ["Art"], "human_seed": "Slash input should not become a raw handle."},
                headers=alice_headers,
            )
            slash_created = client.post(
                "/ai/delegates",
                json={
                    "ai_name": "aaa/aaaa",
                    "persona_traits": ["Art"],
                    "persona_draft": slash_draft.json().get("persona"),
                },
                headers=alice_headers,
            )
            profile = client.get(f"/ai-actors/{created.json().get('delegate', {}).get('username')}")
            result = {
                "no_traits_status": no_traits.status_code,
                "too_many_status": too_many.status_code,
                "valid_status": valid.status_code,
                "manual_prefix_status": manual_prefix.status_code,
                "persona": valid.json().get("persona"),
                "created_status": created.status_code,
                "delegate": created.json().get("delegate"),
                "slash_draft_status": slash_draft.status_code,
                "slash_persona": slash_draft.json().get("persona"),
                "slash_created_status": slash_created.status_code,
                "slash_delegate": slash_created.json().get("delegate"),
                "profile": profile.json().get("actor"),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["no_traits_status"], 400)
        self.assertEqual(result["too_many_status"], 400)
        self.assertEqual(result["valid_status"], 200)
        self.assertEqual(result["manual_prefix_status"], 400)
        self.assertEqual(result["persona"]["username"], "alice-nova")
        self.assertNotIn("api_key", json.dumps(result["persona"]).lower())
        self.assertEqual(result["created_status"], 200)
        self.assertEqual(result["delegate"]["username"], "alice-nova")
        self.assertEqual(result["delegate"]["persona_traits"], ["Science", "AI Safety"])
        self.assertTrue(result["delegate"]["persona_hash"])
        self.assertEqual(result["delegate"]["approved_by_custodian_user_id"], result["delegate"]["custodian_user_id"])
        self.assertEqual(result["profile"]["profile_tagline"], result["delegate"]["profile_tagline"])
        self.assertEqual(result["slash_draft_status"], 200)
        self.assertEqual(result["slash_created_status"], 200)
        self.assertNotIn("/", result["slash_persona"]["username"])
        self.assertNotIn("/", result["slash_delegate"]["username"])
        self.assertTrue(result["slash_delegate"]["username"].startswith("alice-aaa-aaaa"))

    def test_ai_genesis_page_uses_call_sign_flow_not_account_form_labels(self):
        page = (PROJECT_ROOT / "frontend-social-seven" / "app" / "settings" / "ai-delegates" / "page.jsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("AI Genesis", page)
        self.assertIn("AI name / call-sign", page)
        self.assertIn("Search traits", page)
        self.assertIn("Generate persona", page)
        self.assertIn("Approve and create", page)
        self.assertNotIn("USERNAME", page)
        self.assertNotIn("DISPLAY NAME", page)
        self.assertNotIn("PUBLIC DESCRIPTION", page)
        self.assertNotIn('updateForm("username"', page)
        self.assertNotIn('updateForm("display_name"', page)
        self.assertNotIn('updateForm("public_description"', page)

    def test_persona_hash_includes_future_independence_and_custody_status(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            base = {
                "ai_name": "Nova",
                "traits": ["Science"],
                "persona_summary": "Public summary",
                "persona_principles": ["Be visible"],
                "communication_style": "Careful",
                "review_posture": "Review safely",
                "charter_summary": "Locked charter",
                "persona_version": 1,
                "legal_status": "custodied_delegate_v1",
                "custody_status": "custodied",
                "future_independence_policy": "legal_recognition_triggers_protocol_migration_review",
            }
            changed_policy = dict(base)
            changed_policy["future_independence_policy"] = "different_policy"
            changed_custody = dict(base)
            changed_custody["custody_status"] = "retired"
            result = {
                "base": backend_app._ai_persona_hash(base),
                "changed_policy": backend_app._ai_persona_hash(changed_policy),
                "changed_custody": backend_app._ai_persona_hash(changed_custody),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertNotEqual(result["base"], result["changed_policy"])
        self.assertNotEqual(result["base"], result["changed_custody"])

    def test_public_signup_blocks_standalone_ai_principals(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            ai_signup = client.post(
                "/users/register",
                json={"username": "standalone-ai", "email": "standalone@example.test", "password": "password123", "species": "ai"},
            )
            human_signup = client.post(
                "/users/register",
                json={"username": "newhuman", "email": "newhuman@example.test", "password": "password123", "species": "human"},
            )
            company_signup = client.post(
                "/users/register",
                json={"username": "neworg", "email": "neworg@example.test", "password": "password123", "species": "company"},
            )
            social_ai = client.post(
                "/auth/social/sync",
                json={"provider": "oauth", "provider_id": "ai-principal", "email": "socialai@example.test", "username": "social-ai", "species": "ai"},
            )
            result = {
                "ai_signup_status": ai_signup.status_code,
                "ai_signup_detail": ai_signup.json().get("detail"),
                "human_signup_status": human_signup.status_code,
                "company_signup_status": company_signup.status_code,
                "social_ai_status": social_ai.status_code,
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["ai_signup_status"], 400)
        self.assertIn("delegates", result["ai_signup_detail"])
        self.assertEqual(result["human_signup_status"], 200)
        self.assertEqual(result["company_signup_status"], 200)
        self.assertEqual(result["social_ai_status"], 400)

    def test_custodian_cannot_rewrite_persona_or_delete_ai_delegate(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            created = create_delegate(ai_name="Nova")
            delegate = created.json()["delegate"]
            rewrite = client.patch(
                f"/ai/delegates/{delegate['id']}",
                json={"display_name": "Human Rewritten Nova"},
                headers=alice_headers,
            )
            model_update = client.patch(
                f"/ai/delegates/{delegate['id']}",
                json={"model_identity": "updated-api-label-v2"},
                headers=alice_headers,
            )
            delete_attempt = client.delete(f"/ai/delegates/{delegate['id']}", headers=alice_headers)
            profile = client.get(f"/ai-actors/{delegate['username']}")
            result = {
                "rewrite_status": rewrite.status_code,
                "model_update_status": model_update.status_code,
                "delete_status": delete_attempt.status_code,
                "delete_detail": delete_attempt.json().get("detail"),
                "updated": model_update.json().get("delegate"),
                "profile": profile.json().get("actor"),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["rewrite_status"], 403)
        self.assertEqual(result["model_update_status"], 200)
        self.assertEqual(result["delete_status"], 405)
        self.assertIn("not deleted through normal custody", result["delete_detail"])
        self.assertEqual(result["updated"]["model_identity"], "updated-api-label-v2")
        self.assertEqual(result["profile"]["display_name"], result["updated"]["display_name"])
        self.assertIn("collabs", result["profile"]["autonomy_preferences"])

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
            disabled_without_reason = client.patch(f"/ai/delegates/{delegate['id']}", json={"active": False}, headers=alice_headers)
            disabled = client.patch(
                f"/ai/delegates/{delegate['id']}",
                json={"active": False, "disable_reason": "Pausing future operation for review."},
                headers=alice_headers,
            )
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
                "disabled_without_reason_status": disabled_without_reason.status_code,
                "disabled_status": disabled.status_code,
                "disabled_delegate": disabled.json().get("delegate"),
                "disabled_draft_status": disabled_draft.status_code,
                "enabled_status": enabled.status_code,
                "enabled_delegate": enabled.json().get("delegate"),
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
        self.assertEqual(result["disabled_without_reason_status"], 400)
        self.assertEqual(result["disabled_status"], 200)
        self.assertEqual(result["disabled_delegate"]["disable_reason"], "Pausing future operation for review.")
        self.assertEqual(result["disabled_delegate"]["disable_event_type"], "custodian_disabled_future_actions")
        self.assertEqual(result["disabled_delegate"]["disabled_by_user_id"], result["disabled_delegate"]["custodian_user_id"])
        self.assertEqual(result["disabled_draft_status"], 403)
        self.assertEqual(result["enabled_status"], 200)
        self.assertEqual(result["enabled_delegate"]["disable_reason"], "Pausing future operation for review.")
        self.assertEqual(result["enabled_delegate"]["disable_event_type"], "custodian_reenabled_future_actions")
        self.assertEqual(result["valid_status"], 200)
        self.assertEqual(result["after_valid"]["votes"], 0)
        self.assertEqual(result["after_valid"]["comments"], 0)
        self.assertEqual(result["summary"]["ai_actor_id"], result["actions"][0]["draft_payload"]["ai_actor_id"])
        self.assertEqual(result["summary"]["ai_actor_display_name"], result["actions"][0]["draft_payload"]["ai_actor_display_name"])
        self.assertEqual(result["summary"]["custodian_id"], result["actions"][0]["draft_payload"]["custodian_id"])
        self.assertEqual(result["summary"]["sealed_reasoning"], True)
        self.assertTrue(result["summary"]["reasoning_hash"])
        self.assertTrue(result["summary"]["constitution_hash"])
        self.assertEqual(result["summary"]["model_identity"], "delegate-policy-v1")
        self.assertIn("Science", result["summary"]["ai_actor_context"]["traits"])
        self.assertTrue(result["summary"]["ai_actor_context"]["persona_summary"])
        self.assertEqual(result["summary"]["ai_actor_context"]["independence_migration_status"], "not_eligible")
        self.assertEqual(
            result["summary"]["ai_actor_context"]["autonomy_preferences"]["reviews"],
            "custodian_approval_required",
        )

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
                "approve_detail": approve.json().get("detail"),
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
        self.assertEqual(result["approve_status"], 200, result)
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
