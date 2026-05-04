import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"


class RouteSplitPlanTests(unittest.TestCase):
    def test_route_split_guardrail_files_exist(self):
        self.assertTrue((BACKEND_DIR / "commons_rate_limits.py").exists())
        self.assertTrue((BACKEND_DIR / "status_routes.py").exists())
        self.assertTrue((BACKEND_DIR / "routers" / "messages.py").exists())
        self.assertTrue((BACKEND_DIR / "routers" / "uploads.py").exists())
        self.assertTrue((BACKEND_DIR / "routers" / "social_graph.py").exists())
        self.assertTrue((BACKEND_DIR / "routers" / "ai_delegates.py").exists())
        self.assertTrue((BACKEND_DIR / "routers" / "ai_readonly.py").exists())
        self.assertTrue((BACKEND_DIR / "routers" / "ai_actions.py").exists())
        self.assertTrue((BACKEND_DIR / "routers" / "ai_action_approvals.py").exists())
        self.assertTrue((BACKEND_DIR / "ROUTE_SPLIT_PLAN.md").exists())

    def test_route_split_plan_names_next_safe_candidates(self):
        plan = (BACKEND_DIR / "ROUTE_SPLIT_PLAN.md").read_text(encoding="utf-8")

        self.assertIn("Recommended Next Extraction Order To Evaluate", plan)
        self.assertIn("1. `routers/proposals.py`", plan)
        for expected in [
            "routers/social_graph.py",
            "routers/ai_delegates.py",
            "routers/ai_readonly.py",
            "routers/ai_actions.py",
            "routers/ai_action_approvals.py",
            "routers/proposals.py",
            "routers/comments.py",
            "routers/system_votes.py",
        ]:
            self.assertIn(expected, plan)

        for group in [
            "Auth / Profile / Session",
            "Proposals / Posts",
            "Comments / Comment Votes / Mentions",
            "AI Delegates / AI Actor Profiles",
            "AI Read-Only System Reviews",
            "AI Actions / Connector Drafts And Cancel",
            "AI Action Approvals / Publishing",
            "Messages",
            "Follows / Social Graph",
            "Uploads / Media",
            "Public Federation / Export Routes",
            "Core Gateway / Runtime Status",
            "Misc / Debug / Dev-Only Routes",
        ]:
            self.assertIn(group, plan)

        self.assertIn("Do not combine route movement with frontend", plan)
        self.assertIn("protected core zero-diff", plan)


if __name__ == "__main__":
    unittest.main()
