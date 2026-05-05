from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "super-nova-2177"
CORE_ROOT = APP_ROOT / "backend" / "supernova_2177_ui_weighted"


class NestedLegacySurfacesAuditTests(unittest.TestCase):
    def test_nested_audit_exists_and_defers_deletion(self):
        audit_path = ROOT / "NESTED_LEGACY_SURFACES_AUDIT.md"
        self.assertTrue(audit_path.exists())
        audit = audit_path.read_text(encoding="utf-8")

        self.assertIn("Audit-only", audit)
        self.assertIn("nova-web Audit Result", audit)
        self.assertIn("nova-api Audit Result", audit)
        self.assertIn("transcendental_resonance_frontend Audit Result", audit)
        self.assertIn("Protected Core Status", audit)
        self.assertIn("No nested folder was deleted", audit)
        self.assertIn("External deployment/project-root settings were not manually verified", audit)

    def test_nested_sources_and_protected_core_remain_present(self):
        self.assertTrue((CORE_ROOT / "nova-web").is_dir())
        self.assertTrue((CORE_ROOT / "nova-api").is_dir())
        self.assertTrue((CORE_ROOT / "transcendental_resonance_frontend").is_dir())
        self.assertTrue((CORE_ROOT / "supernovacore.py").is_file())
        self.assertTrue((APP_ROOT / "frontend-vite-basic" / "supernovacore.py").is_file())

    def test_cleanup_docs_point_to_nested_audit(self):
        roadmap = (ROOT / "LEGACY_CLEANUP_ROADMAP.md").read_text(encoding="utf-8")
        maintenance = (ROOT / "MAINTENANCE_AUDIT.md").read_text(encoding="utf-8")
        status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        snapshot = (ROOT / "CLEANUP_CANDIDATES_SNAPSHOT.md").read_text(encoding="utf-8")

        for content in (roadmap, maintenance, status, snapshot):
            self.assertIn("NESTED_LEGACY_SURFACES_AUDIT.md", content)

        self.assertIn("do not delete", status.lower())
        self.assertIn("supernovacore.py", roadmap)


if __name__ == "__main__":
    unittest.main()
