from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "super-nova-2177"


class CleanupLauncherRetirementTests(unittest.TestCase):
    def test_frontend_professional_launcher_is_retired_without_source_deletion(self):
        self.assertTrue((APP_ROOT / "frontend-professional").is_dir())
        self.assertFalse((APP_ROOT / "start_frontend_professional.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertNotIn('"professional"', run_local)
        self.assertNotIn("frontend-professional", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"2" = "__retired_frontend_professional"', launcher)
        self.assertIn("frontend-professional local launchers were retired", launcher)
        self.assertNotIn('"frontend-professional" = 5173', launcher)


if __name__ == "__main__":
    unittest.main()
