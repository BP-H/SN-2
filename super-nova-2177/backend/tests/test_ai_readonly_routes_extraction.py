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


class AiReadonlyRoutesExtractionTests(unittest.TestCase):
    def test_ai_readonly_routes_are_registered_from_dedicated_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "ai_readonly.py").read_text(encoding="utf-8")

        self.assertIn("from .routers.ai_readonly import create_ai_readonly_router", app_text)
        self.assertIn("app.include_router(create_ai_readonly_router(", app_text)
        for decorator in [
            '@app.get("/proposals/{proposal_id}/system-ai-review"',
            '@app.get("/proposals/{proposal_id}/ai-review-ledger"',
        ]:
            self.assertNotIn(decorator, app_text)
        for decorator in [
            '@router.get("/proposals/{proposal_id}/system-ai-review"',
            '@router.get("/proposals/{proposal_id}/ai-review-ledger"',
        ]:
            self.assertIn(decorator, module_text)

        registered = {}
        for route in backend_app.app.routes:
            path = getattr(route, "path", "")
            if path in {"/proposals/{proposal_id}/system-ai-review", "/proposals/{proposal_id}/ai-review-ledger"}:
                registered.setdefault(path, set()).update(getattr(route, "methods", set()) or set())
        self.assertIn("GET", registered["/proposals/{proposal_id}/system-ai-review"])
        self.assertIn("GET", registered["/proposals/{proposal_id}/ai-review-ledger"])

    def test_ai_action_approval_publishing_routes_remain_in_backend_app(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "ai_readonly.py").read_text(encoding="utf-8")

        for route in [
            '@app.post("/connector/actions/{action_id}/approve-ai-review"',
            '@app.post("/connector/actions/{action_id}/approve-ai-comment"',
            '@app.post("/connector/actions/{action_id}/approve-ai-post"',
        ]:
            self.assertIn(route, app_text)
            self.assertNotIn(route.replace("@app.", "@router."), module_text)

    def test_unknown_proposal_behavior_is_preserved(self):
        review = client.get("/proposals/987654321/system-ai-review")
        ledger = client.get("/proposals/987654321/ai-review-ledger")

        self.assertEqual(review.status_code, 404)
        self.assertEqual(ledger.status_code, 404)
        self.assertEqual(review.json(), {"detail": "Proposal not found"})
        self.assertEqual(ledger.json(), {"detail": "Proposal not found"})


if __name__ == "__main__":
    unittest.main()
