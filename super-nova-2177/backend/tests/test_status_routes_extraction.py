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


class StatusRoutesExtractionTests(unittest.TestCase):
    def test_status_routes_are_registered_from_dedicated_module(self):
        app_text = (BACKEND_DIR / "app.py").read_text(encoding="utf-8")
        module_text = (BACKEND_DIR / "status_routes.py").read_text(encoding="utf-8")

        self.assertIn("from .status_routes import build_supernova_runtime_payload, create_status_router", app_text)
        self.assertIn("app.include_router(create_status_router(", app_text)
        self.assertNotIn('@app.get("/health"', app_text)
        self.assertNotIn('@app.get("/supernova-status"', app_text)
        self.assertNotIn('@app.get("/status"', app_text)
        self.assertIn('@router.get("/health"', module_text)
        self.assertIn('@router.get("/supernova-status"', module_text)
        self.assertIn('@router.get("/status"', module_text)

    def test_health_response_shape_is_preserved(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            set(payload.keys()),
            {
                "ok",
                "database",
                "database_engine",
                "cors_mode",
                "open_federation_mode",
                "cors_credentials",
                "allowed_origins_count",
                "cors_warning",
                "cors_note",
                "identity_model",
                "supernova_integration",
                "supernova",
                "timestamp",
            },
        )
        self.assertTrue(payload["ok"])
        self.assertIn(payload["database"], {"connected", "disconnected"})
        self.assertIn(payload["supernova_integration"], {"connected", "disconnected"})
        self.assertIn("core_routes_sample", payload["supernova"])
        self.assertNotIn("core_routes", payload["supernova"])

    def test_supernova_status_response_shape_is_preserved(self):
        response = client.get("/supernova-status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(
            set(payload.keys()),
            {
                "supernova_connected",
                "supernova",
                "database_engine",
                "cors_mode",
                "open_federation_mode",
                "cors_credentials",
                "allowed_origins_count",
                "cors_warning",
                "cors_note",
                "identity_model",
                "features_available",
            },
        )
        self.assertEqual(
            set(payload["features_available"].keys()),
            {
                "weighted_voting",
                "karma_system",
                "governance",
                "core_routes",
                "search_filters",
                "advanced_sorting",
            },
        )

    def test_status_response_shape_is_preserved(self):
        response = client.get("/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(set(payload.keys()), {"status", "timestamp", "metrics", "mission"})
        self.assertEqual(payload["status"], "online")
        self.assertEqual(
            set(payload["metrics"].keys()),
            {
                "total_harmonizers",
                "total_vibenodes",
                "community_wellspring",
                "current_system_entropy",
            },
        )


if __name__ == "__main__":
    unittest.main()
