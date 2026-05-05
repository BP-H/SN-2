from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "super-nova-2177"


class CleanupLauncherRetirementTests(unittest.TestCase):
    def test_frontend_professional_source_is_deleted_after_launcher_retirement(self):
        self.assertFalse((APP_ROOT / "frontend-professional").exists())
        self.assertFalse((APP_ROOT / "start_frontend_professional.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertNotIn('"professional"', run_local)
        self.assertNotIn("frontend-professional", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"2" = "__retired_frontend_professional"', launcher)
        self.assertIn("frontend-professional local launchers were retired", launcher)
        self.assertNotIn('"frontend-professional" = 5173', launcher)

        repo_status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active social frontend: `frontend-social-seven`", repo_status)
        self.assertIn("The only active/default frontend is `frontend-social-seven`", repo_status)

        roadmap = (ROOT / "LEGACY_CLEANUP_ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py", roadmap)
        self.assertIn("frontend-professional` | Deleted after launcher retirement", roadmap)

    def test_frontend_vite_3d_launcher_is_retired_without_source_deletion(self):
        self.assertTrue((APP_ROOT / "frontend-vite-3d").is_dir())
        self.assertFalse((APP_ROOT / "start_frontend_vite_3d.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertNotIn('"vite-3d"', run_local)
        self.assertNotIn("frontend-vite-3d", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"3" = "__retired_frontend_vite_3d"', launcher)
        self.assertIn("frontend-vite-3d local launchers were retired", launcher)
        self.assertNotIn('"frontend-vite-3d" = 5175', launcher)

        repo_status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active social frontend: `frontend-social-seven`", repo_status)
        self.assertIn("The only active/default frontend is `frontend-social-seven`", repo_status)

        roadmap = (ROOT / "LEGACY_CLEANUP_ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("frontend-vite-3d` | Source retained; runnable local launcher support retired", roadmap)
        self.assertIn("super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py", roadmap)

        audit = (ROOT / "FRONTEND_VITE_3D_DEPLOYMENT_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("Deletion is deferred", audit)
        self.assertIn("vercel.json", audit)
        self.assertIn("api/ Audit", audit)
        self.assertIn("manual Vercel/project-root", audit)
        self.assertIn("verification", audit)

    def test_frontend_next_launcher_is_retired_without_source_deletion(self):
        self.assertTrue((APP_ROOT / "frontend-next").is_dir())
        self.assertFalse((APP_ROOT / "start_frontend_next.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertNotIn('"next": {', run_local)
        self.assertNotIn("frontend-next", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"1" = "__retired_frontend_next"', launcher)
        self.assertIn("frontend-next local launchers were retired", launcher)
        self.assertNotIn('"frontend-next" = 3000', launcher)

        repo_status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active social frontend: `frontend-social-seven`", repo_status)
        self.assertIn("The only active/default frontend is `frontend-social-seven`", repo_status)

        roadmap = (ROOT / "LEGACY_CLEANUP_ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("frontend-next` | Source retained; runnable local launcher support retired", roadmap)
        self.assertIn("super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py", roadmap)

        audit = (ROOT / "FRONTEND_NEXT_DEPLOYMENT_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("Deletion is deferred", audit)
        self.assertIn("Dockerfile", audit)
        self.assertIn("app/api/ai", audit)
        self.assertIn("Supabase auth", audit)
        self.assertIn("manual Vercel/project-root", audit)

    def test_frontend_social_six_auth_audit_defers_launcher_retirement(self):
        self.assertTrue((APP_ROOT / "frontend-social-six").is_dir())
        self.assertTrue((APP_ROOT / "start_frontend_social_six.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertIn('"social-six": {', run_local)
        self.assertIn("frontend-social-six", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"6" = "frontend-social-six"', launcher)
        self.assertIn('"frontend-social-six" = 3001', launcher)

        repo_status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active social frontend: `frontend-social-seven`", repo_status)
        self.assertIn("frontend-social-six` (source and launcher retained", repo_status)

        audit = (ROOT / "FRONTEND_SOCIAL_SIX_AUTH_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("Launcher retirement and source deletion are deferred", audit)
        self.assertIn("Supabase auth", audit)
        self.assertIn("SOCIAL_AUTH_SETUP.md", audit)
        self.assertIn("app/api/ai", audit)
        self.assertIn("Manual Vercel", audit)
        self.assertIn("Railway", audit)


if __name__ == "__main__":
    unittest.main()
