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


class AiActionRoutesExtractionTests(unittest.TestCase):
    def test_ai_action_draft_list_cancel_routes_are_registered_from_dedicated_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "ai_actions.py").read_text(encoding="utf-8")

        self.assertIn("from .routers.ai_actions import create_ai_actions_router", app_text)
        self.assertIn("app.include_router(create_ai_actions_router(", app_text)
        moved_decorators = [
            '@get("/connector/actions"',
            '@post("/connector/actions/{action_id}/cancel"',
            '@post("/connector/actions/draft-vote"',
            '@post("/connector/actions/draft-ai-review"',
            '@post("/connector/actions/draft-ai-delegate-review"',
            '@post("/connector/actions/draft-ai-delegate-comment"',
            '@post("/connector/actions/draft-ai-delegate-post"',
            '@post("/connector/actions/draft-comment"',
            '@post("/connector/actions/draft-proposal"',
            '@post("/connector/actions/draft-collab-request"',
        ]
        for decorator in moved_decorators:
            self.assertNotIn(decorator.replace("@", "@app."), app_text)
            self.assertIn(decorator.replace("@", "@router."), module_text)

        registered = {}
        expected_paths = {
            "/connector/actions",
            "/connector/actions/{action_id}/cancel",
            "/connector/actions/draft-vote",
            "/connector/actions/draft-ai-review",
            "/connector/actions/draft-ai-delegate-review",
            "/connector/actions/draft-ai-delegate-comment",
            "/connector/actions/draft-ai-delegate-post",
            "/connector/actions/draft-comment",
            "/connector/actions/draft-proposal",
            "/connector/actions/draft-collab-request",
        }
        for route in backend_app.app.routes:
            path = getattr(route, "path", "")
            if path in expected_paths:
                registered.setdefault(path, set()).update(getattr(route, "methods", set()) or set())

        self.assertIn("GET", registered["/connector/actions"])
        for path in expected_paths - {"/connector/actions"}:
            self.assertIn("POST", registered[path])

    def test_ai_action_approval_publishing_routes_are_not_in_draft_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "ai_actions.py").read_text(encoding="utf-8")

        for route in [
            '@post("/connector/actions/{action_id}/approve-vote"',
            '@post("/connector/actions/{action_id}/approve-ai-review"',
            '@post("/connector/actions/{action_id}/approve-ai-comment"',
            '@post("/connector/actions/{action_id}/approve-ai-post"',
        ]:
            self.assertNotIn(route.replace("@", "@app."), app_text)
            self.assertNotIn(route.replace("@", "@router."), module_text)

    def test_cancel_unknown_action_behavior_is_preserved(self):
        response = client.post("/connector/actions/987654321/cancel")

        self.assertIn(response.status_code, {401, 403})


if __name__ == "__main__":
    unittest.main()
