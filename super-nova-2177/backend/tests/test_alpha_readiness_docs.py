import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = ROOT.parent
BACKEND_DIR = ROOT / "backend"


class AlphaReadinessDocsTests(unittest.TestCase):
    def test_route_split_plan_marks_extractions_and_defers_helpers(self):
        plan = (BACKEND_DIR / "ROUTE_SPLIT_PLAN.md").read_text(encoding="utf-8")

        for expected in [
            "backend/status_routes.py",
            "backend/routers/messages.py",
            "backend/routers/uploads.py",
            "backend/routers/social_graph.py",
            "backend/routers/ai_delegates.py",
            "backend/routers/ai_readonly.py",
            "backend/routers/ai_actions.py",
            "backend/routers/ai_action_approvals.py",
            "backend/routers/proposals.py",
            "backend/routers/comments.py",
            "backend/routers/system_votes.py",
        ]:
            self.assertIn(expected, plan)

        self.assertIn("Deeper helper extraction is intentionally deferred", plan)
        self.assertIn("proposal, comment, or", plan)
        self.assertIn("vote helpers merely to reduce", plan)

    def test_branch_protection_doc_names_candidate_required_checks(self):
        status_doc = (REPO_ROOT / "BRANCH_PROTECTION_ROLLOUT_STATUS.md").read_text(encoding="utf-8")

        self.assertIn("Candidate Required Checks", status_doc)
        self.assertIn("Backend local deterministic checks", status_doc)
        self.assertIn("FE7 local deterministic checks", status_doc)
        self.assertIn("Require status checks to pass before merging", status_doc)
        self.assertIn("Require branches to be up to date before merging", status_doc)
        self.assertIn("Keep live/network smoke checks advisory", status_doc)
        self.assertIn("SUPERNOVA_RATE_LIMIT_ENABLED=false", status_doc)

    def test_alpha_smoke_doc_covers_core_manual_paths(self):
        smoke = (REPO_ROOT / "ALPHA_SMOKE_NOW.md").read_text(encoding="utf-8")

        for expected in [
            "ALPHA_SMOKE_SIGNOFF_TEMPLATE.md",
            "commit SHA",
            "frontend URL",
            "backend URL",
            "browser/device",
            "rollback target",
            "AI delegate",
            "AI review draft",
            "AI comment draft",
            "AI post draft",
            "comment",
            "Reply to a comment",
            "Upload a fresh image",
            "data:image/...",
            "cannot reconstruct bytes that are already",
            "/uploads/...",
            "older uploaded image",
            "Messages",
            "Signed-out feed read",
            "Signed-out profile read",
            "Signed-out proposal detail read",
            "/health",
            "/supernova-status",
            "/status",
            "rate limits",
            "Backend local",
            "FE7 local",
            "advisory E2E checks unrequired",
        ]:
            self.assertIn(expected, smoke)

        checklist = (REPO_ROOT / "ALPHA_QA_CHECKLIST.md").read_text(encoding="utf-8")
        self.assertIn("ALPHA_SMOKE_NOW.md", checklist)
        self.assertIn("ALPHA_SMOKE_SIGNOFF_TEMPLATE.md", checklist)
        self.assertIn("bounded DB-backed `data:image/...` fallback", checklist)
        self.assertIn("cannot be reconstructed from app code alone", checklist)
        self.assertIn("Persistent object storage", checklist)

    def test_alpha_smoke_signoff_template_captures_required_evidence(self):
        template = (REPO_ROOT / "ALPHA_SMOKE_SIGNOFF_TEMPLATE.md").read_text(encoding="utf-8")

        for expected in [
            "Commit SHA",
            "Frontend URL",
            "Backend URL",
            "Browser and version",
            "Device / viewport",
            "Smoke date",
            "Previous known-good rollback target",
            "PASS",
            "FAIL",
            "BLOCKED",
            "Known Issues",
            "Rollback target",
            "Require status checks to pass before merging",
            "Require branches to be up to date before merging",
            "Backend local deterministic checks",
            "FE7 local deterministic checks",
            "E2E remains advisory",
            "cannot be reconstructed by app code alone",
        ]:
            self.assertIn(expected, template)

    def test_incomplete_alpha_smoke_signoff_does_not_invent_results(self):
        signoff = (REPO_ROOT / "ALPHA_SMOKE_SIGNOFF_2026-05-04_INCOMPLETE.md").read_text(
            encoding="utf-8"
        )

        for expected in [
            "Incomplete",
            "NOT PROVIDED",
            "NOT RUN",
            "No manual smoke evidence was provided",
            "BLOCKED - no completed manual smoke results were provided",
            "Backend local deterministic checks",
            "FE7 local deterministic checks",
            "cannot be reconstructed by app code alone",
        ]:
            self.assertIn(expected, signoff)

    def test_current_alpha_smoke_signoff_records_only_observed_evidence(self):
        signoff = (REPO_ROOT / "ALPHA_SMOKE_SIGNOFF_2026-05-05.md").read_text(
            encoding="utf-8"
        )

        for expected in [
            "fadfed8f1fb2d14199fa5e2e8a769c61e2d63ec9",
            "Automated Evidence",
            "Manual Evidence Intake",
            "no human-clicked smoke notes",
            "manual smoke rows remain `NOT RUN`",
            "Backend start/check: PASS",
            "/proposals?filter=latest&limit=30",
            "PASS, `PLAYWRIGHT_PORT=3017 npm run test:e2e`",
            "PASS, `PLAYWRIGHT_REAL_BACKEND=1",
            "Manual Smoke Rows",
            "NOT RUN",
            "No human-clicked manual browser smoke evidence was provided",
            "BLOCKED - automated guardrails and advisory real-backend E2E passed",
            "Branch protection has not been verified as enabled",
            "cannot be reconstructed by app code alone",
        ]:
            self.assertIn(expected, signoff)


if __name__ == "__main__":
    unittest.main()
