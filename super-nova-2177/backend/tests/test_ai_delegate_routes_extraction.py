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


class AiDelegateRoutesExtractionTests(unittest.TestCase):
    def test_ai_delegate_routes_are_registered_from_dedicated_router(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "ai_delegates.py").read_text(encoding="utf-8")

        self.assertIn("from .routers.ai_delegates import create_ai_delegates_router", app_text)
        self.assertIn("app.include_router(create_ai_delegates_router(", app_text)
        for decorator in [
            '@app.get("/ai/delegates"',
            '@app.post("/ai/delegates/persona-draft"',
            '@app.post("/ai/delegates"',
            '@app.patch("/ai/delegates/{delegate_id}"',
            '@app.delete("/ai/delegates/{delegate_id}"',
            '@app.get("/ai-actors/{username}"',
        ]:
            self.assertNotIn(decorator, app_text)
        for decorator in [
            '@router.get("/ai/delegates"',
            '@router.post("/ai/delegates/persona-draft"',
            '@router.post("/ai/delegates"',
            '@router.patch("/ai/delegates/{delegate_id}"',
            '@router.delete("/ai/delegates/{delegate_id}"',
            '@router.get("/ai-actors/{username}"',
        ]:
            self.assertIn(decorator, module_text)

        registered = {}
        for route in backend_app.app.routes:
            path = getattr(route, "path", "")
            if path in {"/ai/delegates", "/ai/delegates/persona-draft", "/ai/delegates/{delegate_id}", "/ai-actors/{username}"}:
                registered.setdefault(path, set()).update(getattr(route, "methods", set()) or set())
        self.assertIn("GET", registered["/ai/delegates"])
        self.assertIn("POST", registered["/ai/delegates"])
        self.assertIn("POST", registered["/ai/delegates/persona-draft"])
        self.assertIn("PATCH", registered["/ai/delegates/{delegate_id}"])
        self.assertIn("DELETE", registered["/ai/delegates/{delegate_id}"])
        self.assertIn("GET", registered["/ai-actors/{username}"])

    def test_ai_action_approval_routes_remain_in_backend_app(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "routers" / "ai_delegates.py").read_text(encoding="utf-8")

        for route in [
            '@app.post("/connector/actions/{action_id}/approve-ai-review"',
            '@app.post("/connector/actions/{action_id}/approve-ai-comment"',
        ]:
            self.assertIn(route, app_text)
            self.assertNotIn(route.replace("@app.", "@router."), module_text)

    def test_delete_refusal_response_shape_is_preserved(self):
        response = client.delete("/ai/delegates/123")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "AI delegate identities are not deleted through normal custody. Use disable or retire status. "
                    "Admin, legal, privacy, abuse, and security removal paths are reserved where required."
                )
            },
        )

    def test_system_ai_profile_response_shape_is_preserved(self):
        response = client.get("/ai-actors/supernova-ai")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "public_read_only")
        self.assertEqual(payload["actor"]["username"], "supernova-ai")
        self.assertEqual(payload["actor"]["ai_actor_type"], "system_protocol_agent")
        self.assertTrue(payload["safety"]["advisory"])


if __name__ == "__main__":
    unittest.main()
