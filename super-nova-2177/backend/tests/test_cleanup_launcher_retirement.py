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

    def test_deleted_frontends_are_not_relisted_as_active_inventory_candidates(self):
        inventory_script = (ROOT / "scripts" / "list_cleanup_candidates.py").read_text(
            encoding="utf-8"
        )
        snapshot = (ROOT / "CLEANUP_CANDIDATES_SNAPSHOT.md").read_text(encoding="utf-8")
        candidate_section = snapshot.split("## Legacy Or Experimental Frontend Trees", 1)[1].split(
            "## Nested Backend Experiments", 1
        )[0]

        self.assertNotIn("frontend-nova", inventory_script)
        self.assertNotIn("frontend-professional", inventory_script)
        self.assertNotIn("frontend-vite-3d", inventory_script)
        self.assertNotIn("frontend-next", inventory_script)
        self.assertNotIn("frontend-social-six", inventory_script)
        self.assertNotIn("super-nova-2177/frontend-nova", candidate_section)
        self.assertNotIn("super-nova-2177/frontend-professional", candidate_section)
        self.assertNotIn("super-nova-2177/frontend-vite-3d", candidate_section)
        self.assertNotIn("super-nova-2177/frontend-next", candidate_section)
        self.assertNotIn("super-nova-2177/frontend-social-six", candidate_section)
        self.assertIn("Completed entries are history, not active cleanup candidates.", snapshot)

    def test_frontend_vite_3d_source_is_deleted_after_owner_accepted_risk(self):
        self.assertFalse((APP_ROOT / "frontend-vite-3d").exists())
        self.assertFalse((APP_ROOT / "start_frontend_vite_3d.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertNotIn('"vite-3d"', run_local)
        self.assertNotIn("frontend-vite-3d", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"3" = "__retired_frontend_vite_3d"', launcher)
        self.assertIn("frontend-vite-3d was deleted after launcher retirement", launcher)
        self.assertNotIn('"frontend-vite-3d" = 5175', launcher)

        repo_status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active social frontend: `frontend-social-seven`", repo_status)
        self.assertIn("The only active/default frontend is `frontend-social-seven`", repo_status)
        self.assertIn("frontend-vite-3d`", repo_status)
        self.assertIn("frontend-next`", repo_status)
        self.assertIn("frontend-social-six` were deleted after launcher retirement", repo_status)

        roadmap = (ROOT / "LEGACY_CLEANUP_ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("frontend-vite-3d` | Deleted after runnable local launcher retirement", roadmap)
        self.assertIn("owner explicitly accepted the remaining external Vercel/API-route uncertainty", roadmap)
        self.assertIn("super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py", roadmap)

        audit = (ROOT / "FRONTEND_VITE_3D_DEPLOYMENT_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("Owner-Accepted Deletion", audit)
        self.assertIn("owner explicitly accepted the remaining external uncertainty", audit)
        self.assertIn("vercel.json", audit)
        self.assertIn("api/ Audit", audit)
        self.assertIn("external Vercel/API-route risk", audit)
        self.assertIn("verification", audit)
        self.assertIn("2026-05-05 Deletion Gate Recheck", audit)
        self.assertIn("Deletion was previously blocked", audit)
        self.assertIn("Missing external verification", audit)
        self.assertIn("No Vercel dashboard/API evidence", audit)
        self.assertIn("No DNS/domain evidence", audit)
        self.assertIn("No environment-variable audit", audit)
        self.assertIn("No external smoke/manual QA evidence", audit)

        inventory_script = (ROOT / "scripts" / "list_cleanup_candidates.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("super-nova-2177/frontend-vite-3d", inventory_script)

    def test_frontend_next_source_is_deleted_after_owner_accepted_risk(self):
        self.assertFalse((APP_ROOT / "frontend-next" / "package.json").exists())
        self.assertFalse((APP_ROOT / "frontend-next" / "Dockerfile").exists())
        self.assertFalse((APP_ROOT / "frontend-next" / "app" / "api" / "ai" / "route.js").exists())
        self.assertFalse((APP_ROOT / "start_frontend_next.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertNotIn('"next": {', run_local)
        self.assertNotIn("frontend-next", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"1" = "__retired_frontend_next"', launcher)
        self.assertIn("frontend-next was deleted after launcher retirement", launcher)
        self.assertNotIn('"frontend-next" = 3000', launcher)

        repo_status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active social frontend: `frontend-social-seven`", repo_status)
        self.assertIn("The only active/default frontend is `frontend-social-seven`", repo_status)
        self.assertIn("frontend-next`", repo_status)
        self.assertIn("frontend-social-six` were deleted after launcher retirement", repo_status)

        roadmap = (ROOT / "LEGACY_CLEANUP_ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("frontend-next` | Deleted after runnable local launcher retirement", roadmap)
        self.assertIn("owner explicitly accepted the remaining external deployment/auth/API-route uncertainty", roadmap)
        self.assertIn("super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py", roadmap)

        audit = (ROOT / "FRONTEND_NEXT_DEPLOYMENT_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("Owner-Accepted Deletion", audit)
        self.assertIn("owner explicitly accepted the remaining external uncertainty", audit)
        self.assertIn("Dockerfile", audit)
        self.assertIn("app/api/ai", audit)
        self.assertIn("Supabase auth", audit)
        self.assertIn("external deployment/auth/API-route risk", audit)

    def test_frontend_social_six_source_and_launcher_are_deleted_after_owner_accepted_risk(self):
        self.assertFalse((APP_ROOT / "frontend-social-six" / "package.json").exists())
        self.assertFalse((APP_ROOT / "frontend-social-six" / "Dockerfile").exists())
        self.assertFalse((APP_ROOT / "frontend-social-six" / "SOCIAL_AUTH_SETUP.md").exists())
        self.assertFalse((APP_ROOT / "frontend-social-six" / "supabaseClient.js").exists())
        self.assertFalse((APP_ROOT / "frontend-social-six" / "app" / "api" / "ai" / "route.js").exists())
        self.assertFalse((APP_ROOT / "start_frontend_social_six.ps1").exists())

        run_local = (APP_ROOT / "run_local.py").read_text(encoding="utf-8")
        self.assertNotIn('"social-six": {', run_local)
        self.assertNotIn("frontend-social-six", run_local)

        launcher = (APP_ROOT / "start_supernova.ps1").read_text(encoding="utf-8")
        self.assertIn('"6" = "__retired_frontend_social_six"', launcher)
        self.assertIn("frontend-social-six was deleted after launcher retirement", launcher)
        self.assertNotIn('"frontend-social-six" = 3001', launcher)

        repo_status = (APP_ROOT / "REPO_STATUS.md").read_text(encoding="utf-8")
        self.assertIn("Active social frontend: `frontend-social-seven`", repo_status)
        self.assertIn("frontend-social-six` were deleted after launcher retirement", repo_status)

        audit = (ROOT / "FRONTEND_SOCIAL_SIX_AUTH_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("Owner-Accepted Deletion", audit)
        self.assertIn("owner explicitly accepted the remaining external uncertainty", audit)
        self.assertIn("Supabase auth", audit)
        self.assertIn("SOCIAL_AUTH_SETUP.md", audit)
        self.assertIn("app/api/ai", audit)
        self.assertIn("external Supabase/Vercel/Railway/auth/API-route risk", audit)


if __name__ == "__main__":
    unittest.main()
