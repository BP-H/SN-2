import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for path in (ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import backend.app as backend_app  # noqa: E402


class SystemVoteRoutesExtractionTests(unittest.TestCase):
    def test_system_vote_routes_are_registered_from_dedicated_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "system_votes.py").read_text(encoding="utf-8")

        self.assertIn("from .routers.system_votes import create_system_votes_router", app_text)
        self.assertIn("app.include_router(create_system_votes_router(", app_text)
        for app_decorator in [
            '@app.get("/system-vote"',
            '@app.get("/system-vote/config"',
            '@app.post("/system-vote"',
            '@app.delete("/system-vote"',
        ]:
            self.assertNotIn(app_decorator, app_text)

        for route_path in [
            '"/system-vote"',
            '"/system-vote/config"',
        ]:
            self.assertIn(f"router.add_api_route(\n        {route_path}", module_text)

        registered = {}
        expected = {
            "/system-vote": {"GET", "POST", "DELETE"},
            "/system-vote/config": {"GET"},
        }
        for route in backend_app.app.routes:
            path = getattr(route, "path", "")
            if path in expected:
                registered.setdefault(path, set()).update(getattr(route, "methods", set()) or set())

        self.assertEqual({path: expected[path] for path in expected}, registered)

    def test_proposal_comment_and_ai_routes_are_not_in_system_vote_router(self):
        module_text = (BACKEND_DIR / "routers" / "system_votes.py").read_text(encoding="utf-8")

        for route_fragment in [
            '"/proposals"',
            '"/proposals/{pid}"',
            '"/comments"',
            '"/comments/{comment_id}"',
            '"/connector/actions"',
            '"/connector/actions/{action_id}/approve-ai-review"',
            '"/votes"',
        ]:
            self.assertNotIn(route_fragment, module_text)


if __name__ == "__main__":
    unittest.main()
