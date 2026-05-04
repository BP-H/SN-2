import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for path in (ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import backend.app as backend_app  # noqa: E402


client = TestClient(backend_app.app)


class AiActionApprovalRoutesExtractionTests(unittest.TestCase):
    def test_ai_action_approval_routes_are_registered_from_dedicated_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "ai_action_approvals.py").read_text(encoding="utf-8")

        self.assertIn("from .routers.ai_action_approvals import create_ai_action_approvals_router", app_text)
        self.assertIn("app.include_router(create_ai_action_approvals_router(", app_text)
        moved_decorators = [
            '@post("/connector/actions/{action_id}/approve-vote"',
            '@post("/connector/actions/{action_id}/approve-ai-review"',
            '@post("/connector/actions/{action_id}/approve-ai-comment"',
            '@post("/connector/actions/{action_id}/approve-ai-post"',
        ]
        for decorator in moved_decorators:
            self.assertNotIn(decorator.replace("@", "@app."), app_text)
            self.assertIn(decorator.replace("@", "@router."), module_text)

        registered = {}
        expected_paths = {
            "/connector/actions/{action_id}/approve-vote",
            "/connector/actions/{action_id}/approve-ai-review",
            "/connector/actions/{action_id}/approve-ai-comment",
            "/connector/actions/{action_id}/approve-ai-post",
        }
        for route in backend_app.app.routes:
            path = getattr(route, "path", "")
            if path in expected_paths:
                registered.setdefault(path, set()).update(getattr(route, "methods", set()) or set())

        for path in expected_paths:
            self.assertIn("POST", registered[path])

    def test_system_vote_route_wrappers_remain_outside_ai_approval_router(self):
        module_text = (BACKEND_DIR / "routers" / "ai_action_approvals.py").read_text(encoding="utf-8")

        for route in [
            '"/system-vote"',
            '"/system-vote/config"',
        ]:
            self.assertNotIn(route, module_text)

        for moved_proposal_route in [
            '@router.get("/proposals"',
            '@router.post("/proposals"',
            '@router.patch("/proposals/{pid}"',
            '@router.delete("/proposals/{pid}"',
        ]:
            self.assertNotIn(moved_proposal_route, module_text)

        for moved_comment_route in [
            '@router.get("/comments"',
            '@router.post("/comments"',
            '@router.patch("/comments/{comment_id}"',
            '@router.delete("/comments/{comment_id}"',
        ]:
            self.assertNotIn(moved_comment_route, module_text)

    def test_unknown_approval_still_requires_auth_before_not_found(self):
        response = client.post("/connector/actions/987654321/approve-vote")

        self.assertIn(response.status_code, {401, 403})


if __name__ == "__main__":
    unittest.main()
