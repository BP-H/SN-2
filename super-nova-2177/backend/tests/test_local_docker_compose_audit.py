from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = ROOT / "super-nova-2177"


class LocalDockerComposeAuditTests(unittest.TestCase):
    def test_audit_exists_and_marks_project_compose_stale_local_only(self):
        audit_path = ROOT / "LOCAL_DOCKER_COMPOSE_AUDIT.md"
        self.assertTrue(audit_path.exists())
        audit = audit_path.read_text(encoding="utf-8")

        for expected in [
            "Audit-only",
            "super-nova-2177/docker-compose.yml",
            "builds `./frontend`",
            "super-nova-2177/frontend",
            "does not exist",
            "frontend-social-seven",
            "Stale local-only Compose candidate",
            "do not invoke Docker Compose",
        ]:
            self.assertIn(expected, audit)

    def test_audit_records_nested_compose_and_dockerfile_surfaces(self):
        audit = (ROOT / "LOCAL_DOCKER_COMPOSE_AUDIT.md").read_text(encoding="utf-8")

        for expected in [
            "super-nova-2177/backend/supernova_2177_ui_weighted/docker-compose.yml",
            "super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml",
            "NESTED_LEGACY_SURFACES_AUDIT.md",
            "super-nova-2177/backend/Dockerfile",
            "super-nova-2177/frontend-social-seven/Dockerfile",
            "super-nova-2177/frontend-next/Dockerfile",
            "super-nova-2177/frontend-social-six/Dockerfile",
            "super-nova-2177/backend/supernova_2177_ui_weighted/nova-api/Dockerfile",
        ]:
            self.assertIn(expected, audit)

    def test_compose_config_remains_unchanged_by_audit(self):
        self.assertFalse((ROOT / "docker-compose.yml").exists())
        self.assertFalse((APP_ROOT / "frontend").exists())

        compose = (APP_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("supernova_frontend", compose)
        self.assertIn("build: ./frontend", compose)
        self.assertNotIn("frontend-social-seven", compose)

    def test_docs_point_to_local_docker_compose_audit(self):
        for path in [
            ROOT / "MAINTENANCE_AUDIT.md",
            ROOT / "CLEANUP_CANDIDATES_SNAPSHOT.md",
            ROOT / "CLEANUP_STABILITY_CHECKPOINT.md",
            ROOT / "LEGACY_CLEANUP_ROADMAP.md",
            APP_ROOT / "REPO_STATUS.md",
        ]:
            self.assertIn(
                "LOCAL_DOCKER_COMPOSE_AUDIT.md",
                path.read_text(encoding="utf-8"),
                msg=f"{path} should point to the local Docker Compose audit",
            )


if __name__ == "__main__":
    unittest.main()
