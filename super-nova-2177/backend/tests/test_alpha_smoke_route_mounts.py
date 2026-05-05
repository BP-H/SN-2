import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for path in (ROOT, BACKEND_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

import backend.app as backend_app  # noqa: E402


def _mounted_methods() -> dict[str, set[str]]:
    mounted: dict[str, set[str]] = {}
    for route in backend_app.app.routes:
        path = getattr(route, "path", "")
        if not path:
            continue
        mounted.setdefault(path, set()).update(getattr(route, "methods", set()) or set())
    return mounted


class AlphaSmokeRouteMountTests(unittest.TestCase):
    def test_smoke_checklist_routes_remain_registered(self):
        mounted = _mounted_methods()
        expected = {
            "/health": {"GET"},
            "/supernova-status": {"GET"},
            "/status": {"GET"},
            "/proposals": {"GET", "POST", "DELETE"},
            "/comments": {"GET", "POST"},
            "/messages": {"GET", "POST"},
            "/upload-image": {"POST"},
            "/upload-file": {"POST"},
            "/follows": {"GET", "POST", "DELETE"},
            "/social-users": {"GET"},
            "/system-vote": {"GET", "POST", "DELETE"},
            "/ai/delegates": {"GET", "POST"},
            "/connector/actions": {"GET"},
            "/connector/actions/{action_id}/approve-vote": {"POST"},
            "/connector/actions/{action_id}/approve-ai-review": {"POST"},
            "/connector/actions/{action_id}/approve-ai-comment": {"POST"},
            "/connector/actions/{action_id}/approve-ai-post": {"POST"},
        }

        missing = {}
        for path, methods in expected.items():
            registered = mounted.get(path, set())
            absent = sorted(methods - registered)
            if absent:
                missing[path] = absent

        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
