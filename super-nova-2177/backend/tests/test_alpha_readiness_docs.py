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
        self.assertIn("Keep live/network smoke checks advisory", status_doc)
        self.assertIn("SUPERNOVA_RATE_LIMIT_ENABLED=false", status_doc)

    def test_alpha_smoke_doc_covers_core_manual_paths(self):
        smoke = (REPO_ROOT / "ALPHA_SMOKE_NOW.md").read_text(encoding="utf-8")

        for expected in [
            "AI delegate",
            "AI review draft",
            "AI comment draft",
            "AI post draft",
            "comment",
            "Reply to a comment",
            "Upload a fresh image",
            "older uploaded image",
            "Messages",
            "Signed-out feed read",
            "Signed-out profile read",
            "Signed-out proposal detail read",
            "/health",
            "/supernova-status",
            "/status",
            "rate limits",
        ]:
            self.assertIn(expected, smoke)

        checklist = (REPO_ROOT / "ALPHA_QA_CHECKLIST.md").read_text(encoding="utf-8")
        self.assertIn("ALPHA_SMOKE_NOW.md", checklist)


if __name__ == "__main__":
    unittest.main()
