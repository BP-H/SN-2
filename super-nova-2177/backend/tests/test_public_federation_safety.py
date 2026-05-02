import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for path in (ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import backend.app as backend_app  # noqa: E402


app = backend_app.app


client = TestClient(app)
PROTOCOL_FILENAMES = {
    "supernova.organization.schema.json",
    "supernova.execution-intent.schema.json",
    "supernova.three-species-vote.schema.json",
    "supernova.portable-profile.schema.json",
}
PROTOCOL_EXAMPLE_FILENAMES = {
    "example-organization-manifest.json",
    "example-execution-intent.json",
    "example-three-species-vote.json",
    "example-portable-profile.json",
}


class PublicFederationSafetyTests(unittest.TestCase):
    def test_supernova_manifest_declares_manual_read_only_governance(self):
        response = client.get("/.well-known/supernova")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["federation"]["mode"], "read_only_discovery")
        self.assertFalse(payload["federation"]["activitypub_inbox"])
        self.assertFalse(payload["federation"]["webmention_receiver"])
        self.assertFalse(payload["federation"]["remote_feed_mutation"])

        governance = payload["governance"]
        self.assertEqual(governance["species"], ["human", "ai", "company"])
        self.assertTrue(governance["three_species_protocol"])
        self.assertEqual(governance["execution_current_mode"], "manual_preview_only")
        self.assertFalse(governance["automatic_execution"])
        self.assertTrue(governance["company_ratification_required"])
        self.assertFalse(governance["ai_execution_without_ratification"])

        organization = payload["organization_integration"]
        self.assertEqual(organization["status"], "planned")
        self.assertFalse(organization["automatic_execution"])
        self.assertFalse(organization["company_webhooks"])
        self.assertEqual(organization["allowed_actions"], [])

        schemas = payload["protocol_schemas"]
        self.assertTrue(schemas["organization_manifest"].endswith("/protocol/supernova.organization.schema.json"))
        self.assertTrue(schemas["execution_intent"].endswith("/protocol/supernova.execution-intent.schema.json"))
        self.assertTrue(schemas["three_species_vote"].endswith("/protocol/supernova.three-species-vote.schema.json"))
        self.assertTrue(schemas["portable_profile"].endswith("/protocol/supernova.portable-profile.schema.json"))
        self.assertTrue(schemas["examples"].endswith("/protocol/examples/"))
        self.assertIn("/domain-verification/preview", payload["endpoints"]["domain_verification_preview"])

        examples = payload["protocol_examples"]
        self.assertTrue(examples["organization_manifest"].endswith("/protocol/examples/example-organization-manifest.json"))
        self.assertTrue(examples["execution_intent"].endswith("/protocol/examples/example-execution-intent.json"))
        self.assertTrue(examples["three_species_vote"].endswith("/protocol/examples/example-three-species-vote.json"))
        self.assertTrue(examples["portable_profile"].endswith("/protocol/examples/example-portable-profile.json"))

        version_policy = payload["schema_version_policy"]
        self.assertEqual(version_policy["current_version"], "v1")
        self.assertEqual(version_policy["v1_execution_posture"], "manual_preview_only")
        self.assertFalse(version_policy["v1_automatic_execution"])
        self.assertFalse(version_policy["v1_company_webhooks"])
        self.assertTrue(version_policy["breaking_changes_require_new_schema_version"])

    def test_protocol_schema_files_are_public_static_json(self):
        for path, schema_name in {
            "/protocol/supernova.organization.schema.json": "supernova.organization_manifest.v1",
            "/protocol/supernova.execution-intent.schema.json": "supernova.execution_intent.v1",
            "/protocol/supernova.three-species-vote.schema.json": "supernova.three_species_vote.v1",
            "/protocol/supernova.portable-profile.schema.json": "supernova.portable_profile.v1",
        }.items():
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["properties"]["schema"]["const"], schema_name)
            if path.endswith("supernova.organization.schema.json"):
                equal_weight = payload["properties"]["governance"]["properties"]["equal_species_weight"]
                self.assertTrue(equal_weight["const"])

    def test_backend_protocol_mirror_exists_for_backend_only_deploys(self):
        backend_protocol_dir = BACKEND_DIR / "protocol"
        self.assertTrue(backend_protocol_dir.exists())
        self.assertTrue(all((backend_protocol_dir / name).exists() for name in PROTOCOL_FILENAMES))
        self.assertTrue(all((backend_protocol_dir / "examples" / name).exists() for name in PROTOCOL_EXAMPLE_FILENAMES))
        for name in PROTOCOL_FILENAMES:
            self.assertEqual((ROOT / "protocol" / name).read_bytes(), (backend_protocol_dir / name).read_bytes())
        for name in PROTOCOL_EXAMPLE_FILENAMES:
            root_example = ROOT / "protocol" / "examples" / name
            backend_example = backend_protocol_dir / "examples" / name
            self.assertEqual(root_example.read_bytes(), backend_example.read_bytes())

    def test_protocol_examples_are_public_and_keep_v1_manual_only(self):
        for path, schema_name in {
            "/protocol/examples/example-organization-manifest.json": "supernova.organization_manifest.v1",
            "/protocol/examples/example-execution-intent.json": "supernova.execution_intent.v1",
            "/protocol/examples/example-three-species-vote.json": "supernova.three_species_vote.v1",
            "/protocol/examples/example-portable-profile.json": "supernova.portable_profile.v1",
        }.items():
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["schema"], schema_name)

        organization = client.get("/protocol/examples/example-organization-manifest.json").json()
        self.assertFalse(organization["execution"]["automatic_execution"])
        self.assertFalse(organization["execution"]["webhooks_enabled"])
        self.assertEqual(organization["execution"]["allowed_actions"], [])

        intent = client.get("/protocol/examples/example-execution-intent.json").json()
        self.assertEqual(intent["execution_mode"], "manual_preview_only")
        self.assertFalse(intent["automatic_execution"])
        self.assertTrue(intent["requires_company_ratification"])
        self.assertTrue(intent["requires_human_supervision"])

        vote = client.get("/protocol/examples/example-three-species-vote.json").json()
        self.assertEqual(vote["execution"]["execution_current_mode"], "manual_preview_only")
        self.assertFalse(vote["execution"]["automatic_execution"])
        self.assertTrue(vote["execution"]["company_ratification_required"])

        profile = client.get("/protocol/examples/example-portable-profile.json").json()
        self.assertFalse(profile["identity"]["domain_verified"])
        self.assertTrue(profile["privacy"]["public_export_only"])
        self.assertIn("direct_messages", profile["privacy"]["excluded_fields"])

    def test_public_manifest_keeps_private_export_fields_excluded(self):
        response = client.get("/.well-known/supernova")
        self.assertEqual(response.status_code, 200)
        excluded = set(response.json()["public_data_policy"]["excluded_fields"])

        self.assertTrue({
            "email",
            "password_hash",
            "access_token",
            "refresh_token",
            "direct_messages",
            "private_message_metadata",
            "secrets",
            "admin_state",
            "debug_state",
        }.issubset(excluded))

    def test_proposal_governance_payload_stays_manual_and_non_executing(self):
        payload = backend_app._proposal_governance_payload({
            "governance_kind": "decision",
            "decision_level": "important",
            "voting_days": 7,
            "automatic_execution": True,
            "webhook": "https://example.com/hook",
            "external_action": "deploy",
        })

        self.assertIsNotNone(payload)
        self.assertEqual(payload["kind"], "decision")
        self.assertEqual(payload["execution_mode"], "manual")
        self.assertEqual(payload["execution_status"], "pending_vote")
        self.assertEqual(payload["voting_days"], 7)

        forbidden_keys = {
            "automatic_execution",
            "webhook",
            "webhooks",
            "external_action",
            "allowed_actions",
            "execution_intent",
        }
        self.assertTrue(forbidden_keys.isdisjoint(payload.keys()))

        non_decision = backend_app._proposal_governance_payload({"governance_kind": "discussion"})
        self.assertIsNone(non_decision)

    def test_actual_portable_profile_export_declares_public_only_privacy(self):
        identity = {
            "username": "alice",
            "display_name": "alice",
            "species": "human",
            "bio": "",
            "avatar_url": "",
            "local_profile_url": "https://2177.tech/users/alice",
            "canonical_url": "https://2177.tech/users/alice",
            "canonical_url_source": "supernova",
            "canonical_url_verified": False,
            "domain_url": "",
            "claimed_domain": "",
            "claimed_domain_url": "",
            "domain_as_profile": False,
            "domain_verified": False,
            "verified_domain": "",
            "verified_domain_url": "",
            "verified_at": None,
            "verification_method": None,
            "did": "",
            "actor_url": "https://2177.tech/actors/alice",
            "portable_export_url": "https://2177.tech/u/alice/export.json",
            "verification_file": "/.well-known/supernova.json",
            "verification_template": {},
        }
        profile_payload = {
            "username": "alice",
            "display_name": "alice",
            "species": "human",
            "bio": "",
            "avatar_url": "",
            "domain_url": "",
            "domain_as_profile": False,
        }
        public_posts = [{
            "id": "proposal-1",
            "url": "https://2177.tech/proposals/1",
            "created_at": "2026-04-26T00:00:00Z",
        }]

        with patch.object(backend_app, "_profile_exists", return_value=True), patch.object(
            backend_app, "_profile_identity_payload", return_value=identity
        ), patch.object(backend_app, "profile", return_value=profile_payload), patch.object(
            backend_app, "list_proposals", return_value=public_posts
        ):
            response = client.get("/u/alice/export.json")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema"], "supernova.portable_profile.v1")
        self.assertEqual(payload["identity"], identity)
        self.assertEqual(payload["profile"], profile_payload)
        self.assertEqual(payload["public_posts"], public_posts)

        governance = payload["governance"]
        self.assertEqual(governance["species_model"], "three_species_equal_vote")
        self.assertEqual(governance["execution_current_mode"], "manual_preview_only")
        self.assertFalse(governance["automatic_execution"])
        self.assertTrue(governance["human_supervision_required"])

        privacy = payload["privacy"]
        self.assertTrue(privacy["public_export_only"])
        excluded = set(privacy["excluded_fields"])
        forbidden_keys = {
            "email",
            "password_hash",
            "access_token",
            "refresh_token",
            "direct_messages",
            "private_message_metadata",
            "secrets",
            "admin_state",
            "debug_state",
        }
        self.assertTrue(forbidden_keys.issubset(excluded))

        def walk_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from walk_keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from walk_keys(child)

        self.assertTrue(forbidden_keys.isdisjoint(set(walk_keys(payload))))

    def test_domain_verification_preview_does_not_verify_or_mutate(self):
        response = client.get("/domain-verification/preview?domain=example.com&username=alice")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["status"], "preview_only")
        self.assertTrue(payload["does_not_verify_yet"])
        self.assertEqual(payload["domain"], "example.com")
        self.assertEqual(payload["methods"]["https_well_known"]["url"], "https://example.com/.well-known/supernova")
        expected_example = payload["methods"]["https_well_known"]["expected_example"]
        self.assertEqual(expected_example["organization"]["name"], "alice")
        self.assertEqual(expected_example["governance"]["species"], ["human", "ai", "company"])
        self.assertTrue(expected_example["governance"]["three_species_protocol"])
        self.assertTrue(expected_example["governance"]["company_ratification_required"])
        self.assertTrue(expected_example["governance"]["human_supervision_required"])
        self.assertEqual(expected_example["value_sharing"]["status"], "not_financial_protocol")
        self.assertTrue(expected_example["value_sharing"]["company_side_policy_required"])
        self.assertTrue(expected_example["value_sharing"]["supernova_nonprofit_does_not_custody_funds"])
        self.assertEqual(payload["methods"]["dns_txt"]["name"], "_supernova.example.com")
        self.assertFalse(payload["safety"]["external_fetch"])
        self.assertFalse(payload["safety"]["dns_lookup"])
        self.assertFalse(payload["safety"]["database_write"])
        self.assertFalse(payload["safety"]["marks_domain_verified"])

    def test_write_federation_and_execution_routes_are_not_registered(self):
        blocked_posts = {
            "/webmention",
            "/actors/{username}/inbox",
            "/actors/{username}/outbox",
            "/execute",
            "/execution",
        }

        for route in app.routes:
            methods = getattr(route, "methods", set()) or set()
            path = getattr(route, "path", "")
            self.assertFalse(path in blocked_posts and "POST" in methods)

        for path in ("/execute", "/execution", "/webmention", "/actors/test/inbox", "/actors/test/outbox"):
            self.assertIn(client.post(path).status_code, {404, 405})

    def test_system_vote_records_tally_without_execution_side_effects(self):
        class FakeResult:
            def fetchall(self):
                return [
                    SimpleNamespace(username="alice", choice="yes", voter_type="human"),
                ]

        class FakeDb:
            def __init__(self):
                self.statements = []
                self.commits = 0

            def execute(self, statement, params=None):
                self.statements.append(str(statement))
                return FakeResult()

            def commit(self):
                self.commits += 1

            def rollback(self):
                raise AssertionError("system vote safety path should not roll back")

        fake_db = FakeDb()
        payload = backend_app.SystemVoteIn(username="alice", choice="yes", voter_type="ai")

        with patch.object(backend_app, "_ensure_system_votes_table", lambda db: None), patch.object(
            backend_app, "_species_for_username", return_value="human"
        ), patch.object(
            backend_app, "_require_token_identity_match", return_value=SimpleNamespace(username="alice")
        ), patch.object(
            backend_app, "_enforce_system_vote_deadline", lambda: None
        ):
            result = backend_app.cast_system_vote(payload, db=fake_db)

        self.assertEqual(result["user_vote"], "like")
        self.assertEqual(result["likes"], [{"voter": "alice", "type": "human"}])
        self.assertEqual(result["dislikes"], [])
        self.assertEqual(result["total"], 1)
        self.assertEqual(fake_db.commits, 1)

        forbidden_result_keys = {
            "execution",
            "execution_mode",
            "execution_status",
            "execution_intent",
            "webhook",
            "webhooks",
            "external_action",
            "automatic_execution",
        }
        self.assertTrue(forbidden_result_keys.isdisjoint(result.keys()))

        statement_text = " ".join(fake_db.statements).lower()
        self.assertNotIn("execution", statement_text)
        self.assertNotIn("webhook", statement_text)

    def test_social_sync_preserves_existing_account_species_and_rejects_ai_mutation(self):
        existing = SimpleNamespace(
            id=2177,
            username="alice",
            email="alice@example.com",
            species="company",
            profile_pic="custom.jpg",
            is_active=False,
            consent_given=False,
        )

        class FakeDb:
            def __init__(self):
                self.added = []
                self.commits = 0
                self.refreshed = []

            def add(self, item):
                self.added.append(item)

            def commit(self):
                self.commits += 1

            def refresh(self, item):
                self.refreshed.append(item)

        fake_db = FakeDb()
        ai_payload = backend_app.SocialAuthSyncIn(
            provider="oauth",
            provider_id="provider-alice",
            email="alice@example.com",
            username="alice",
            avatar_url="",
            species="ai",
        )

        with patch.object(backend_app, "Harmonizer", object), patch.object(
            backend_app, "_find_social_user", return_value=existing
        ):
            with self.assertRaises(backend_app.HTTPException) as error:
                backend_app.sync_social_auth(ai_payload, db=fake_db)

        self.assertEqual(error.exception.status_code, 400)
        self.assertIn("protocol actor type", error.exception.detail)
        self.assertEqual(existing.species, "company")
        self.assertFalse(existing.is_active)
        self.assertFalse(existing.consent_given)
        self.assertEqual(fake_db.added, [])
        self.assertEqual(fake_db.commits, 0)

        payload = backend_app.SocialAuthSyncIn(
            provider="oauth",
            provider_id="provider-alice",
            email="alice@example.com",
            username="alice",
            avatar_url="",
            species="human",
        )

        with patch.object(backend_app, "Harmonizer", object), patch.object(
            backend_app, "_find_social_user", return_value=existing
        ):
            result = backend_app.sync_social_auth(payload, db=fake_db)

        self.assertEqual(existing.species, "company")
        self.assertEqual(result["species"], "company")
        self.assertTrue(existing.is_active)
        self.assertTrue(existing.consent_given)
        self.assertEqual(fake_db.added, [existing])
        self.assertEqual(fake_db.commits, 1)
        self.assertEqual(fake_db.refreshed, [existing])


if __name__ == "__main__":
    unittest.main()
