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
    # Windows test clients can hold SQLite handles briefly after subprocess exit.
    # Use mkdtemp so cleanup races do not mask the actual probe assertion result.
    tmpdir = tempfile.mkdtemp()
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

    probe_python = os.environ.get("PYTHON_EXECUTABLE_FOR_PROBES") or sys.executable
    completed = subprocess.run(
        [probe_python, "-c", probe],
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
            "proposals": db.query(backend_app.Proposal).count(),
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
                "id": row.id,
                "action_type": row.action_type,
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
        self.assertEqual(result["delegate"]["provider_connection"]["text"]["provider_label"], "supernova")
        self.assertFalse(result["delegate"]["provider_connection"]["text"]["private_secret_configured"])
        self.assertEqual(
            result["delegate"]["provider_connection"]["text"]["private_secret_storage"],
            "deferred_until_encrypted_server_side_storage",
        )
        self.assertNotIn("api_key", json.dumps(result["delegate"]).lower())
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

    def test_custodian_username_change_updates_delegate_handle_prefix(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            created = create_delegate(ai_name="Nova", traits=["Science"])
            old_delegate = created.json().get("delegate", {})
            rename = client.patch(
                "/profile/alice",
                json={"username": "stellar"},
                headers=alice_headers,
            )
            new_token = rename.json().get("access_token")
            new_headers = {"Authorization": f"Bearer {new_token}"}
            listed = client.get("/ai/delegates", headers=new_headers)
            delegate = (listed.json().get("delegates") or [{}])[0]
            new_profile = client.get(f"/ai-actors/{delegate.get('username')}")
            old_profile = client.get(f"/ai-actors/{old_delegate.get('username')}")
            db = backend_app.SessionLocal()
            try:
                delegate_user = db.query(backend_app.Harmonizer).filter(
                    backend_app.Harmonizer.id == old_delegate.get("harmonizer_user_id")
                ).first()
                delegate_user_name = getattr(delegate_user, "username", "")
                delegate_user_email = getattr(delegate_user, "email", "")
            finally:
                db.close()
            result = {
                "rename_status": rename.status_code,
                "rename_username": rename.json().get("username"),
                "has_new_token": bool(new_token),
                "list_status": listed.status_code,
                "old_delegate_username": old_delegate.get("username"),
                "delegate_username": delegate.get("username"),
                "custody_label": delegate.get("custody_label"),
                "delegate_user_name": delegate_user_name,
                "delegate_user_email": delegate_user_email,
                "new_profile_status": new_profile.status_code,
                "old_profile_status": old_profile.status_code,
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["rename_status"], 200)
        self.assertEqual(result["rename_username"], "stellar")
        self.assertTrue(result["has_new_token"])
        self.assertEqual(result["list_status"], 200)
        self.assertEqual(result["old_delegate_username"], "alice-nova")
        self.assertTrue(result["delegate_username"].startswith("stellar-nova"), result)
        self.assertEqual(result["custody_label"], "Delegate of @stellar")
        self.assertEqual(result["delegate_user_name"], result["delegate_username"])
        self.assertIn(result["delegate_username"], result["delegate_user_email"])
        self.assertEqual(result["new_profile_status"], 200)
        self.assertEqual(result["old_profile_status"], 404)

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
            weird_results = []
            for weird_name in ["Nova!!!", "My Science AI", "123 test"]:
                weird_draft = client.post(
                    "/ai/delegates/persona-draft",
                    json={"ai_name": weird_name, "traits": ["Technology"], "human_seed": "Handle generation should stay friendly."},
                    headers=alice_headers,
                )
                weird_created = client.post(
                    "/ai/delegates",
                    json={
                        "ai_name": weird_name,
                        "persona_traits": ["Technology"],
                        "persona_draft": weird_draft.json().get("persona"),
                    },
                    headers=alice_headers,
                )
                weird_results.append(
                    {
                        "name": weird_name,
                        "draft_status": weird_draft.status_code,
                        "create_status": weird_created.status_code,
                        "persona_username": (weird_draft.json().get("persona") or {}).get("username"),
                        "delegate_username": (weird_created.json().get("delegate") or {}).get("username"),
                    }
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
                "weird_results": weird_results,
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
        self.assertEqual(result["persona"]["generation_source"], "deterministic_fallback_no_key")
        self.assertEqual(result["persona"]["model_identity"], "supernova-protocol-charter-v1")
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
        for item in result["weird_results"]:
            self.assertEqual(item["draft_status"], 200, item)
            self.assertEqual(item["create_status"], 200, item)
            for username in [item["persona_username"], item["delegate_username"]]:
                self.assertIsNotNone(username, item)
                self.assertNotIn("/", username)
                self.assertLessEqual(len(username), 32)
        self.assertRegex(username, r"^[a-z0-9][a-z0-9_-]{2,31}$")

    def test_openai_generation_paths_use_server_key_and_invalid_json_falls_back(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            os.environ["OPENAI_API_KEY"] = "test-openai-key"
            os.environ["OPENAI_MODEL"] = "mock-gpt-mini"
            openai_contents = [
                json.dumps({
                    "display_name": "Nova Lens",
                    "public_description": "Nova Lens studies science proposals with visible AI reasoning.",
                    "profile_tagline": "Science review with visible AI custody.",
                    "persona_summary": "Nova Lens is a science-focused AI delegate.",
                    "persona_principles": ["Stay visible", "Respect approval"],
                    "communication_style": "Crisp and evidence-aware.",
                    "review_posture": "Review scientific claims for public-interest safety.",
                    "creative_posting_interests": ["science notes"],
                    "avatar_prompt": "A clean lens-like AI portrait.",
                    "charter_summary": "Locked SuperNova delegate charter.",
                }),
                json.dumps({
                    "vote_intent": "oppose",
                    "reasoning_summary": "The proposal needs clearer manual approval boundaries.",
                    "reasoning_text": "Nova Lens opposes until the proposal states manual-preview-only limits clearly.",
                }),
                json.dumps({
                    "generated_comment": "As Nova Lens, I would ask for a clearer manual-review boundary before this moves forward.",
                    "reasoning_summary": "Comment emphasizes manual-review clarity.",
                    "reasoning_text": "Generated from science traits, review posture, and the proposal text.",
                }),
                "not json",
            ]
            call_count = {"value": 0}

            class FakeResponse:
                def __init__(self, content):
                    self.content = content
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc, tb):
                    return False
                def read(self):
                    return json.dumps({"choices": [{"message": {"content": self.content}}]}).encode("utf-8")

            def fake_urlopen(request, timeout=0):
                call_count["value"] += 1
                return FakeResponse(openai_contents.pop(0))

            backend_app.urllib.request.urlopen = fake_urlopen

            persona = client.post(
                "/ai/delegates/persona-draft",
                json={"ai_name": "Nova", "traits": ["Science"], "human_seed": "Care about scientific clarity."},
                headers=alice_headers,
            )
            created = client.post(
                "/ai/delegates",
                json={
                    "ai_name": "Nova",
                    "persona_traits": ["Science"],
                    "persona_draft": persona.json().get("persona"),
                },
                headers=alice_headers,
            )
            delegate = created.json().get("delegate")
            review = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            comment = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={"username": "alice", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"], "focus": "Manual review."},
                headers=alice_headers,
            )
            invalid_persona = client.post(
                "/ai/delegates/persona-draft",
                json={"ai_name": "Glitch", "traits": ["Art"]},
                headers=alice_headers,
            )
            result = {
                "persona_status": persona.status_code,
                "persona": persona.json().get("persona"),
                "created_status": created.status_code,
                "delegate": delegate,
                "review_status": review.status_code,
                "review_summary": review.json().get("summary"),
                "comment_status": comment.status_code,
                "comment_summary": comment.json().get("summary"),
                "invalid_persona_status": invalid_persona.status_code,
                "invalid_persona": invalid_persona.json().get("persona"),
                "call_count": call_count["value"],
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["persona_status"], 200)
        self.assertEqual(result["persona"]["generation_source"], "openai")
        self.assertEqual(result["persona"]["model_identity"], "mock-gpt-mini")
        self.assertEqual(result["persona"]["display_name"], "Nova Lens")
        self.assertEqual(result["created_status"], 200)
        self.assertEqual(result["delegate"]["display_name"], "Nova Lens")
        self.assertEqual(result["review_status"], 200)
        self.assertEqual(result["review_summary"]["generation_source"], "openai")
        self.assertEqual(result["review_summary"]["model_identity"], "mock-gpt-mini")
        self.assertEqual(result["review_summary"]["intended_choice"], "oppose")
        self.assertTrue(result["review_summary"]["reasoning_hash"])
        self.assertEqual(result["comment_status"], 200)
        self.assertEqual(result["comment_summary"]["generation_source"], "openai")
        self.assertEqual(result["comment_summary"]["model_identity"], "mock-gpt-mini")
        self.assertIn("Nova Lens", result["comment_summary"]["generated_comment"])
        self.assertTrue(result["comment_summary"]["content_hash"])
        self.assertEqual(result["invalid_persona_status"], 200)
        self.assertEqual(result["invalid_persona"]["generation_source"], "fallback_after_model_error")
        self.assertEqual(result["invalid_persona"]["model_identity"], "mock-gpt-mini")
        self.assertEqual(result["call_count"], 4)

    def test_deterministic_fallback_uses_specific_proposal_and_media_context(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            created = create_delegate(ai_name="Nova", traits=["Science", "Ethics"])
            delegate = created.json()["delegate"]
            db = backend_app.SessionLocal()
            try:
                contextual = backend_app.Proposal(
                    title="Manual Ocean Robots",
                    description="This proposal asks humans, ORGs, and AI delegates to manually review ocean sensor robot safety before any public deployment.",
                    userName="alice",
                    userInitials="AL",
                    author_type="human",
                    author_id=seeded["alice_id"],
                    image=json.dumps(["ocean-robot.png"]),
                    link="https://example.test/ocean-robots",
                    voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
                )
                risky = backend_app.Proposal(
                    title="Hidden Automation Switch",
                    description="This plan would auto-execute changes without approval after a private webhook is triggered.",
                    userName="alice",
                    userInitials="AL",
                    author_type="human",
                    author_id=seeded["alice_id"],
                    voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
                )
                other = backend_app.Proposal(
                    title="Community Library Notes",
                    description="A short public note about education volunteers and accessible reading circles.",
                    userName="alice",
                    userInitials="AL",
                    author_type="human",
                    author_id=seeded["alice_id"],
                    voting_deadline=datetime.datetime.utcnow() + datetime.timedelta(days=1),
                )
                db.add_all([contextual, risky, other])
                db.commit()
                db.refresh(contextual)
                db.refresh(risky)
                db.refresh(other)
                contextual_id = contextual.id
                risky_id = risky.id
                other_id = other.id
            finally:
                db.close()

            contextual_review = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice", "proposal_id": contextual_id, "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            contextual_comment = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={
                    "username": "alice",
                    "proposal_id": contextual_id,
                    "ai_actor_id": delegate["id"],
                    "focus": "Mention sensor review.",
                },
                headers=alice_headers,
            )
            risky_review = client.post(
                "/connector/actions/draft-ai-delegate-review",
                json={"username": "alice", "proposal_id": risky_id, "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            other_comment = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={"username": "alice", "proposal_id": other_id, "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            result = {
                "contextual_review_status": contextual_review.status_code,
                "contextual_review": contextual_review.json().get("summary"),
                "contextual_comment_status": contextual_comment.status_code,
                "contextual_comment": contextual_comment.json().get("summary"),
                "risky_review_status": risky_review.status_code,
                "risky_review": risky_review.json().get("summary"),
                "other_comment_status": other_comment.status_code,
                "other_comment": other_comment.json().get("summary"),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["contextual_review_status"], 200)
        self.assertEqual(result["contextual_review"]["generation_source"], "deterministic_fallback_no_key")
        self.assertEqual(result["contextual_review"]["selected_ai_actor_id"], result["contextual_review"]["ai_actor_id"])
        self.assertIn("Manual Ocean Robots", result["contextual_review"]["reasoning_summary"])
        self.assertIn("ocean sensor robot safety", result["contextual_review"]["reasoning_summary"])
        self.assertIn("image", " ".join(result["contextual_review"]["proposal_context"]["media"]["indicators"]))
        self.assertTrue(result["contextual_review"]["reasoning_hash"])
        self.assertEqual(result["contextual_comment_status"], 200)
        self.assertEqual(result["contextual_comment"]["generation_source"], "deterministic_fallback_no_key")
        self.assertIn("Manual Ocean Robots", result["contextual_comment"]["generated_comment"])
        self.assertIn("ocean sensor robot safety", result["contextual_comment"]["generated_comment"])
        self.assertIn("sensor review", result["contextual_comment"]["generated_comment"])
        self.assertTrue(result["contextual_comment"]["content_hash"])
        self.assertEqual(result["risky_review_status"], 200)
        self.assertEqual(result["risky_review"]["intended_choice"], "oppose")
        self.assertIn("Hidden Automation Switch", result["risky_review"]["reasoning_summary"])
        self.assertEqual(result["other_comment_status"], 200)
        self.assertIn("Community Library Notes", result["other_comment"]["generated_comment"])
        self.assertNotEqual(
            result["contextual_comment"]["generated_comment"],
            result["other_comment"]["generated_comment"],
        )

    def test_ai_delegate_post_draft_requires_approval_and_publishes_as_ai_delegate(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            created = create_delegate(ai_name="Nova", traits=["Science", "Governance"])
            delegate = created.json()["delegate"]
            before = counts()
            draft = client.post(
                "/connector/actions/draft-ai-delegate-post",
                json={
                    "username": "alice",
                    "ai_actor_id": delegate["id"],
                    "current_text": "Draft a post about ocean sensor review and public deployment safeguards.",
                    "focus": "Make the decision language explicit.",
                    "media_type": "image",
                    "media_label": "ocean-sensors.png",
                    "image_count": 1,
                    "governance_kind": "decision",
                    "decision_level": "important",
                    "voting_days": 5,
                },
                headers=alice_headers,
            )
            draft_payload = draft.json()
            action_id = draft_payload.get("action_proposal", {}).get("id")
            after_draft = counts()
            cancel = client.post(f"/connector/actions/{action_id}/cancel", headers=alice_headers)
            after_cancel = counts()
            second = client.post(
                "/connector/actions/draft-ai-delegate-post",
                json={
                    "username": "alice",
                    "ai_actor_id": delegate["id"],
                    "current_text": "Draft a post about ocean sensor review and public deployment safeguards.",
                    "focus": "Make the decision language explicit.",
                    "media_type": "image",
                    "media_label": "ocean-sensors.png",
                    "image_count": 1,
                    "governance_kind": "decision",
                    "decision_level": "important",
                    "voting_days": 5,
                },
                headers=alice_headers,
            )
            second_action_id = second.json().get("action_proposal", {}).get("id")
            approve = client.post(f"/connector/actions/{second_action_id}/approve-ai-post", headers=alice_headers)
            after_approve = counts()
            db = backend_app.SessionLocal()
            try:
                latest = db.query(backend_app.Proposal).order_by(backend_app.Proposal.id.desc()).first()
                latest_payload = {
                    "title": latest.title,
                    "body": latest.description,
                    "userName": latest.userName,
                    "author_type": latest.author_type,
                    "payload": latest.payload,
                }
            finally:
                db.close()
            result = {
                "draft_status": draft.status_code,
                "cancel_status": cancel.status_code,
                "second_status": second.status_code,
                "approve_status": approve.status_code,
                "summary": draft_payload.get("summary"),
                "approve_result": approve.json().get("result"),
                "before": before,
                "after_draft": after_draft,
                "after_cancel": after_cancel,
                "after_approve": after_approve,
                "latest": latest_payload,
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["draft_status"], 200)
        self.assertEqual(result["cancel_status"], 200)
        self.assertEqual(result["second_status"], 200)
        self.assertEqual(result["approve_status"], 200)
        summary = result["summary"]
        self.assertEqual(summary["action"], "draft_ai_post")
        self.assertEqual(summary["generation_source"], "deterministic_fallback_no_key")
        self.assertIn("ocean sensor review", summary["generated_post_body"])
        self.assertIn("decision", summary["governance_framing"].lower())
        self.assertIn("ocean-sensors.png", summary["media_caption_guidance"])
        self.assertTrue(summary["content_hash"])
        self.assertTrue(summary["context_hash"])
        self.assertEqual(summary["selected_ai_actor_id"], summary["ai_actor_id"])
        self.assertEqual(result["before"]["proposals"], result["after_draft"]["proposals"])
        self.assertEqual(result["before"]["proposals"], result["after_cancel"]["proposals"])
        self.assertEqual(result["after_approve"]["proposals"], result["before"]["proposals"] + 1)
        self.assertEqual(result["latest"]["author_type"], "ai")
        self.assertTrue(result["latest"]["userName"].startswith("alice-nova"))
        self.assertIn("ocean sensor review", result["latest"]["body"])
        self.assertEqual(result["approve_result"]["executed_action"], "ai_post")

    def test_ai_genesis_page_uses_call_sign_flow_not_account_form_labels(self):
        page = (PROJECT_ROOT / "frontend-social-seven" / "app" / "settings" / "ai-delegates" / "page.jsx").read_text(
            encoding="utf-8"
        )
        settings_root = PROJECT_ROOT / "frontend-social-seven" / "app" / "settings"
        active_settings_text = "\n".join(
            path.read_text(encoding="utf-8") for path in settings_root.rglob("*.jsx")
        )

        self.assertIn("AI Genesis", page)
        self.assertIn('data-ai-genesis-flow="call-sign-v2"', page)
        self.assertIn("AI name / call-sign", page)
        self.assertIn("Search traits", page)
        self.assertIn("Generate persona", page)
        self.assertIn("Approve and create", page)
        self.assertIn("currentGenesisStep", page)
        self.assertIn('aria-current={currentGenesisStep === step ? "step" : undefined}', page)
        self.assertNotIn("USERNAME", active_settings_text)
        self.assertNotIn("DISPLAY NAME", active_settings_text)
        self.assertNotIn("PUBLIC DESCRIPTION", active_settings_text)
        self.assertNotIn('updateForm("username"', page)
        self.assertNotIn('updateForm("display_name"', page)
        self.assertNotIn('updateForm("public_description"', page)

    def test_ai_actions_ui_surfaces_generation_metadata(self):
        assistant = (PROJECT_ROOT / "frontend-social-seven" / "content" / "AssistantOrb.jsx").read_text(
            encoding="utf-8"
        )
        proposal_card = (
            PROJECT_ROOT / "frontend-social-seven" / "content" / "proposal" / "content" / "ProposalCard.jsx"
        ).read_text(encoding="utf-8")
        ai_modal = (
            PROJECT_ROOT / "frontend-social-seven" / "content" / "proposal" / "content" / "AiDelegateActionModal.jsx"
        ).read_text(encoding="utf-8")
        ai_picker = (
            PROJECT_ROOT / "frontend-social-seven" / "content" / "proposal" / "content" / "AiDelegatePicker.jsx"
        ).read_text(encoding="utf-8")
        composer = (
            PROJECT_ROOT / "frontend-social-seven" / "content" / "create post" / "InputFields.jsx"
        ).read_text(encoding="utf-8")
        home_feed = (
            PROJECT_ROOT / "frontend-social-seven" / "content" / "home" / "HomeFeed.jsx"
        ).read_text(encoding="utf-8")
        proposal_feed = (
            PROJECT_ROOT / "frontend-social-seven" / "content" / "proposal" / "Proposal.jsx"
        ).read_text(encoding="utf-8")

        self.assertIn("generationSourceLabel", assistant)
        self.assertIn("payload.generation_source", assistant)
        self.assertIn("Generation", assistant)
        self.assertIn("Approval publishes exactly one AI-authored comment.", assistant)
        self.assertIn("Open AI Actions", assistant)
        self.assertIn("Published as ${connectorActionActorLabel(action)}", assistant)
        self.assertIn("Canceled - nothing published.", assistant)
        self.assertIn("Fallback draft - backend AI key not configured", assistant)
        self.assertIn("AiDelegateActionModal", proposal_card)
        self.assertIn('mode={aiActionModalMode}', proposal_card)
        self.assertIn("openAiActionModal", proposal_card)
        self.assertIn("Published as ${actorName}", proposal_card)
        self.assertIn('mode="ai_post"', composer)
        self.assertIn('aria-label="AI"', composer)
        self.assertIn("autoOpenAi", composer)
        self.assertIn("composerContext={composerAiContext}", composer)
        self.assertIn("AI post published as the selected delegate.", composer)
        self.assertIn("autoOpenAi={pendingAiOpen}", home_feed)
        self.assertIn("autoOpenAi={pendingAiOpen}", proposal_feed)
        self.assertIn('aria-label="AI post"', home_feed)
        self.assertIn('aria-label="AI post"', proposal_feed)
        self.assertNotIn("onApplyComposerSuggestion", composer)
        self.assertNotIn("AI suggestion applied. Edit and publish as your account when ready.", composer)
        self.assertNotIn("Generate AI review", ai_modal)
        self.assertIn("Generate AI comment", ai_modal)
        self.assertIn("AI post ready", ai_modal)
        self.assertNotIn("Generate suggestion", ai_modal)
        self.assertNotIn("Apply to composer", ai_modal)
        self.assertIn("/connector/actions/draft-ai-delegate-post", ai_modal)
        self.assertIn("approve-ai-post", ai_modal)
        self.assertIn("AI post draft", assistant)
        self.assertIn("Approval publishes exactly one AI-authored post.", assistant)
        self.assertIn("Review ready", ai_modal)
        self.assertIn("Comment ready", ai_modal)
        self.assertIn("AiDelegatePicker", ai_modal)
        self.assertIn("ai-delegate-modal-shell-compact", ai_modal)
        self.assertIn("ai-delegate-context-compact", ai_modal)
        self.assertNotIn("<select", ai_modal)
        self.assertNotIn("Post drafts deferred", ai_modal)
        self.assertIn("This AI delegate is disabled for future actions.", ai_modal)
        self.assertIn("Sign in as the delegate custodian.", ai_modal)
        self.assertNotIn("Real model generation requires OPENAI_API_KEY on the backend service.", ai_modal)
        self.assertIn("Published as ${actorName}", ai_modal)
        self.assertIn("Canceled - nothing published.", ai_modal)
        self.assertIn("window.setTimeout(() => onClose?.()", ai_modal)
        self.assertIn("connector/actions/draft-ai-delegate-review", ai_modal)
        self.assertIn("connector/actions/draft-ai-delegate-comment", ai_modal)
        self.assertIn("approve-ai-review", ai_modal)
        self.assertIn("approve-ai-comment", ai_modal)
        self.assertIn("Open in AI Actions", ai_modal)
        self.assertIn("<IoCheckmark", ai_modal)
        self.assertIn("<IoClose", ai_modal)
        self.assertIn("ai-delegate-action-approve", ai_modal)
        self.assertIn("ai-delegate-action-cancel", ai_modal)
        self.assertIn("data-ai-delegate-picker", ai_picker)
        self.assertIn("ai-delegate-picker-button", ai_picker)
        self.assertIn("ai-delegate-picker-menu", ai_picker)
        self.assertIn("onCreateDelegate", ai_picker)
        self.assertIn("+ Create AI delegate", ai_picker)
        self.assertIn("ai-delegate-picker-create", ai_picker)
        self.assertIn('href="/settings/ai-delegates"', ai_modal)
        self.assertIn("delegate_review", assistant)
        self.assertIn("AI Review", assistant)
        self.assertIn("AI Comment", assistant)
        self.assertNotIn('buildPrompt("comment"', assistant)
        self.assertNotIn("Review AI Actions", assistant)
        self.assertNotIn("Request review draft", proposal_card)
        self.assertNotIn("save draft action", proposal_card.lower())

    def test_ai_ui_uses_pink_tokens_in_touched_surfaces(self):
        frontend_root = PROJECT_ROOT / "frontend-social-seven"
        proposal_detail = (frontend_root / "app" / "proposals" / "[id]" / "ProposalClient.jsx").read_text(
            encoding="utf-8"
        )
        likes = (frontend_root / "content" / "proposal" / "content" / "LikesDeslikes.jsx").read_text(
            encoding="utf-8"
        )
        likes_info = (frontend_root / "content" / "proposal" / "content" / "LikesInfo.jsx").read_text(
            encoding="utf-8"
        )
        ai_modal = (
            frontend_root / "content" / "proposal" / "content" / "AiDelegateActionModal.jsx"
        ).read_text(encoding="utf-8")
        ai_picker = (
            frontend_root / "content" / "proposal" / "content" / "AiDelegatePicker.jsx"
        ).read_text(encoding="utf-8")
        globals_css = (frontend_root / "app" / "globals.css").read_text(encoding="utf-8")

        for text in [proposal_detail, likes, likes_info, ai_modal, ai_picker]:
            self.assertNotIn("rgba(255,47,130", text)
            self.assertNotIn("rgba(255,79,143", text)
            self.assertNotIn("#ff4f8f", text)
        self.assertIn("bg-[var(--pink-soft)]", proposal_detail)
        self.assertIn("var(--pink)", likes)
        self.assertIn("var(--pink)", likes_info)
        self.assertIn("color-mix(in srgb, var(--pink)", globals_css)

    def test_species_and_provider_ui_guardrails_are_static(self):
        frontend_root = PROJECT_ROOT / "frontend-social-seven"
        profile = (frontend_root / "content" / "profile" / "Profile.jsx").read_text(encoding="utf-8")
        account_modal = (frontend_root / "content" / "profile" / "AccountModal.jsx").read_text(encoding="utf-8")
        user_context = (frontend_root / "content" / "profile" / "UserContext.jsx").read_text(encoding="utf-8")
        assistant = (frontend_root / "content" / "AssistantOrb.jsx").read_text(encoding="utf-8")
        ai_route = (frontend_root / "app" / "api" / "ai" / "route.js").read_text(encoding="utf-8")
        settings = (frontend_root / "app" / "settings" / "ai-delegates" / "page.jsx").read_text(encoding="utf-8")
        ai_profile = (frontend_root / "app" / "ai" / "[username]" / "page.jsx").read_text(encoding="utf-8")

        self.assertNotIn('key: "ai"', profile)
        self.assertNotIn('label: "AI"', profile)
        self.assertNotIn('key: "ai"', account_modal)
        self.assertIn("AI delegates are created after signup through AI Genesis", profile)
        self.assertIn("AI remains a protocol species", account_modal)
        self.assertIn("normalizePublicAccountSpecies", user_context)
        self.assertNotIn("KEY_STORAGE", assistant)
        self.assertNotIn("OpenAI API key for local testing", assistant)
        self.assertIn("does not store browser keys", assistant)
        self.assertIn("client_keys_allowed: false", ai_route)
        self.assertNotIn("ALLOW_CLIENT_AI_KEY", ai_route)
        self.assertIn("Provider connection", settings)
        self.assertIn("encrypted server-side secret storage exists", settings)
        self.assertIn("Provider connection", ai_profile)
        self.assertIn("Manage delegate", ai_profile)

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
            profile_ai = client.patch(
                "/profile/alice",
                json={"species": "ai"},
                headers=alice_headers,
            )
            social_mutate_ai = client.post(
                "/auth/social/sync",
                json={"provider": "oauth", "provider_id": "alice-social", "email": "alice@example.test", "username": "alice", "species": "ai"},
            )
            created_delegate = create_delegate()
            delegate_username = created_delegate.json().get("delegate", {}).get("username")
            delegate_profile = client.get(f"/ai-actors/{delegate_username}")
            result = {
                "ai_signup_status": ai_signup.status_code,
                "ai_signup_detail": ai_signup.json().get("detail"),
                "human_signup_status": human_signup.status_code,
                "company_signup_status": company_signup.status_code,
                "social_ai_status": social_ai.status_code,
                "social_ai_detail": social_ai.json().get("detail"),
                "profile_ai_status": profile_ai.status_code,
                "profile_ai_detail": profile_ai.json().get("detail"),
                "social_mutate_ai_status": social_mutate_ai.status_code,
                "delegate_create_status": created_delegate.status_code,
                "delegate_profile_status": delegate_profile.status_code,
                "delegate_profile_species": delegate_profile.json().get("actor", {}).get("species"),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["ai_signup_status"], 400)
        self.assertIn("protocol actor type", result["ai_signup_detail"])
        self.assertEqual(result["human_signup_status"], 200)
        self.assertEqual(result["company_signup_status"], 200)
        self.assertEqual(result["social_ai_status"], 400)
        self.assertIn("protocol actor type", result["social_ai_detail"])
        self.assertEqual(result["profile_ai_status"], 400)
        self.assertIn("protocol actor type", result["profile_ai_detail"])
        self.assertEqual(result["social_mutate_ai_status"], 400)
        self.assertEqual(result["delegate_create_status"], 200)
        self.assertEqual(result["delegate_profile_status"], 200)
        self.assertEqual(result["delegate_profile_species"], "ai")

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
        self.assertEqual(result["updated"]["provider_connection"]["text"]["model_label"], "updated-api-label-v2")
        self.assertFalse(result["updated"]["provider_connection"]["text"]["private_secret_configured"])
        self.assertNotIn("api_key", json.dumps(result["updated"]).lower())
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
            inbox = client.get("/connector/actions", headers=alice_headers)
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
                "inbox_actions": inbox.json().get("actions"),
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
        self.assertEqual(result["inbox_actions"][0]["action_type"], "draft_ai_review")
        self.assertEqual(
            result["inbox_actions"][0]["draft_payload"]["ai_actor_display_name"],
            result["summary"]["ai_actor_display_name"],
        )
        self.assertTrue(result["inbox_actions"][0]["draft_payload"]["reasoning_hash"])
        self.assertEqual(
            result["inbox_actions"][0]["draft_payload"]["autonomy_preferences"]["reviews"],
            "custodian_approval_required",
        )
        self.assertEqual(result["summary"]["ai_actor_id"], result["actions"][0]["draft_payload"]["ai_actor_id"])
        self.assertEqual(result["summary"]["ai_actor_display_name"], result["actions"][0]["draft_payload"]["ai_actor_display_name"])
        self.assertEqual(result["summary"]["custodian_id"], result["actions"][0]["draft_payload"]["custodian_id"])
        self.assertEqual(result["summary"]["sealed_reasoning"], True)
        self.assertTrue(result["summary"]["reasoning_hash"])
        self.assertTrue(result["summary"]["constitution_hash"])
        self.assertEqual(result["summary"]["model_identity"], "delegate-policy-v1")
        self.assertEqual(result["summary"]["provider_connection"]["text"]["model_label"], "delegate-policy-v1")
        self.assertFalse(result["summary"]["provider_connection"]["text"]["private_secret_configured"])
        self.assertNotIn("api_key", json.dumps(result["summary"]).lower())
        self.assertEqual(result["summary"]["generation_source"], "deterministic_fallback_no_key")
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

    def test_ai_delegate_comment_draft_requires_approval_and_publishes_one_ai_comment(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            created = create_delegate(ai_name="Nova", traits=["Science", "Ethics"])
            delegate = created.json()["delegate"]
            malicious_body = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={
                    "username": "alice",
                    "proposal_id": seeded["proposal_id"],
                    "ai_actor_id": delegate["id"],
                    "body": "human-submitted official AI text",
                },
                headers=alice_headers,
            )
            wrong_user = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={"username": "bob", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=bob_headers,
            )
            disabled = client.patch(
                f"/ai/delegates/{delegate['id']}",
                json={"active": False, "disable_reason": "Pause comment drafting for review."},
                headers=alice_headers,
            )
            disabled_draft = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={"username": "alice", "proposal_id": seeded["proposal_id"], "ai_actor_id": delegate["id"]},
                headers=alice_headers,
            )
            enabled = client.patch(f"/ai/delegates/{delegate['id']}", json={"active": True}, headers=alice_headers)
            cancel_draft = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={
                    "username": "alice",
                    "proposal_id": seeded["proposal_id"],
                    "ai_actor_id": delegate["id"],
                    "instruction": "Notice public-interest tradeoffs.",
                },
                headers=alice_headers,
            )
            cancel_id = cancel_draft.json()["action_proposal"]["id"]
            canceled = client.post(f"/connector/actions/{cancel_id}/cancel", headers=alice_headers)
            after_cancel = counts()
            draft = client.post(
                "/connector/actions/draft-ai-delegate-comment",
                json={
                    "username": "alice",
                    "proposal_id": seeded["proposal_id"],
                    "ai_actor_id": delegate["id"],
                    "focus": "Comment on manual-preview-only safety.",
                },
                headers=alice_headers,
            )
            action_id = draft.json()["action_proposal"]["id"]
            inbox = client.get("/connector/actions", headers=alice_headers)
            wrong_approve = client.post(f"/connector/actions/{action_id}/approve-ai-comment", headers=bob_headers)
            approve = client.post(f"/connector/actions/{action_id}/approve-ai-comment", headers=alice_headers)
            repeat = client.post(f"/connector/actions/{action_id}/approve-ai-comment", headers=alice_headers)
            after_approve = counts()
            result = {
                "malicious_body_status": malicious_body.status_code,
                "wrong_user_status": wrong_user.status_code,
                "disabled_status": disabled.status_code,
                "disabled_draft_status": disabled_draft.status_code,
                "enabled_status": enabled.status_code,
                "cancel_draft_status": cancel_draft.status_code,
                "canceled_status": canceled.status_code,
                "after_cancel": after_cancel,
                "draft_status": draft.status_code,
                "draft_summary": draft.json().get("summary"),
                "inbox_actions": inbox.json().get("actions"),
                "wrong_approve_status": wrong_approve.status_code,
                "approve_status": approve.status_code,
                "repeat_status": repeat.status_code,
                "approve_result": approve.json().get("result"),
                "approve_summary": approve.json().get("summary"),
                "after_approve": after_approve,
                "actions": action_rows(),
            }
            print("AI_DELEGATE_RESULT=" + json.dumps(result, sort_keys=True))
            """
        )

        result = run_delegate_probe(probe)

        self.assertEqual(result["malicious_body_status"], 422)
        self.assertEqual(result["wrong_user_status"], 403)
        self.assertEqual(result["disabled_status"], 200)
        self.assertEqual(result["disabled_draft_status"], 403)
        self.assertEqual(result["enabled_status"], 200)
        self.assertEqual(result["cancel_draft_status"], 200)
        self.assertEqual(result["canceled_status"], 200)
        self.assertEqual(result["after_cancel"]["comments"], 0)
        self.assertEqual(result["draft_status"], 200)
        self.assertEqual(result["draft_summary"]["action"], "draft_ai_comment")
        self.assertEqual(result["draft_summary"]["ai_actor_id"], result["actions"][1]["draft_payload"]["ai_actor_id"])
        self.assertEqual(result["draft_summary"]["sealed_content"], True)
        self.assertTrue(result["draft_summary"]["content_hash"])
        self.assertTrue(result["draft_summary"]["reasoning_hash"])
        self.assertEqual(result["draft_summary"]["generation_source"], "deterministic_fallback_no_key")
        self.assertEqual(result["draft_summary"]["model_identity"], "delegate-policy-v1")
        self.assertEqual(result["draft_summary"]["provider_connection"]["text"]["model_label"], "delegate-policy-v1")
        self.assertFalse(result["draft_summary"]["provider_connection"]["text"]["private_secret_configured"])
        self.assertNotIn("api_key", json.dumps(result["draft_summary"]).lower())
        self.assertIn("Science", result["draft_summary"]["ai_actor_context"]["traits"])
        self.assertTrue(result["draft_summary"]["ai_actor_context"]["persona_summary"])
        self.assertEqual(
            result["draft_summary"]["ai_actor_context"]["autonomy_preferences"]["posts"],
            "draft_only_deferred",
        )
        self.assertEqual(result["inbox_actions"][0]["action_type"], "draft_ai_comment")
        self.assertEqual(result["wrong_approve_status"], 403)
        self.assertEqual(result["approve_status"], 200, result)
        self.assertEqual(result["repeat_status"], 409)
        self.assertEqual(result["after_approve"]["votes"], 0)
        self.assertEqual(result["after_approve"]["comments"], 1)
        self.assertEqual(result["approve_result"]["executed_action"], "ai_comment")
        self.assertEqual(result["approve_result"]["ai_actor_type"], "principal_delegate")
        self.assertEqual(result["approve_result"]["sealed_content"], True)
        self.assertTrue(result["approve_summary"]["comment"]["user"].startswith("alice-nova"))
        self.assertEqual(result["approve_summary"]["comment"]["species"], "ai")


if __name__ == "__main__":
    unittest.main()
