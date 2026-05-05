from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "super-nova-2177"


class CleanupStabilityCheckpointTests(unittest.TestCase):
    def test_checkpoint_exists_and_records_completed_cleanup(self):
        checkpoint_path = ROOT / "CLEANUP_STABILITY_CHECKPOINT.md"
        self.assertTrue(checkpoint_path.exists())
        checkpoint = checkpoint_path.read_text(encoding="utf-8")

        for expected in [
            "Pause broad cleanup",
            "frontend-nova",
            "frontend-professional",
            "frontend-vite-3d",
            "frontend-next",
            "frontend-social-six",
            "Nested legacy surfaces",
            "nova-web",
            "nova-api",
            "transcendental_resonance_frontend",
        ]:
            self.assertIn(expected, checkpoint)

    def test_checkpoint_lists_retained_surfaces_and_protected_core(self):
        checkpoint = (ROOT / "CLEANUP_STABILITY_CHECKPOINT.md").read_text(encoding="utf-8")

        for expected in [
            "super-nova-2177/frontend-social-seven",
            "super-nova-2177/backend/app.py",
            "super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py",
            "super-nova-2177/frontend-vite-basic/supernovacore.py",
            "super-nova-2177/frontend-vite-basic",
            "super-nova-2177/frontend-social-six",
            "super-nova-2177/frontend-next",
            "super-nova-2177/backend/supernova_2177_ui_weighted/nova-web",
            "super-nova-2177/backend/supernova_2177_ui_weighted/nova-api",
            "super-nova-2177/backend/supernova_2177_ui_weighted/transcendental_resonance_frontend",
        ]:
            self.assertIn(expected, checkpoint)

    def test_checkpoint_names_manual_external_verification(self):
        checkpoint = (ROOT / "CLEANUP_STABILITY_CHECKPOINT.md").read_text(encoding="utf-8")

        for expected in [
            "Vercel project roots",
            "Railway and Docker deploy roots",
            "Supabase provider redirect URLs",
            "DNS and domain targets",
            "Durable media storage",
            "old uploaded image bytes",
            "GitHub branch protection required checks",
            "Backend local deterministic checks",
            "FE7 local deterministic checks",
        ]:
            self.assertIn(expected, checkpoint)

    def test_cleanup_docs_point_to_checkpoint(self):
        for path in [
            ROOT / "MAINTENANCE_AUDIT.md",
            ROOT / "CLEANUP_CANDIDATES_SNAPSHOT.md",
            ROOT / "LEGACY_CLEANUP_ROADMAP.md",
            APP_ROOT / "REPO_STATUS.md",
        ]:
            self.assertIn(
                "CLEANUP_STABILITY_CHECKPOINT.md",
                path.read_text(encoding="utf-8"),
                msg=f"{path} should point to the checkpoint",
            )


if __name__ == "__main__":
    unittest.main()
