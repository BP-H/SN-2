import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_probe(probe: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "connector_action_proposals.sqlite"
        secret = "strong-test-secret-for-connector-action-proposals"
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": secret,
                "SUPERNOVA_ENV": "development",
                "APP_ENV": "development",
                "ENV": "development",
            }
        )
        env.pop("RAILWAY_ENVIRONMENT", None)

        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        combined_output = f"{completed.stdout}\n{completed.stderr}"
        if db_path.as_posix() in combined_output or secret in combined_output:
            raise AssertionError("probe printed a DB URL/path or secret value")

    if completed.returncode != 0:
        raise AssertionError(
            f"probe failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    result_lines = [
        line
        for line in completed.stdout.splitlines()
        if line.startswith("CONNECTOR_ACTION_MODEL_RESULT=")
    ]
    if not result_lines:
        raise AssertionError(f"probe result missing\nstdout:\n{completed.stdout}")
    return json.loads(result_lines[-1].split("=", 1)[1])


PROBE = textwrap.dedent(
    """
    import json
    import sys
    from pathlib import Path

    from sqlalchemy import inspect, text

    project_root = Path.cwd()
    backend_dir = project_root / "backend"
    for path in (project_root, backend_dir):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)

    import backend.app as backend_app
    from db_models import (
        Base,
        CONNECTOR_ACTION_PROPOSAL_STATUSES,
        ConnectorActionProposal,
    )


    def current_bind():
        session = backend_app.SessionLocal()
        try:
            return session.get_bind()
        finally:
            session.close()


    def table_columns(db, table_name):
        rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return {
            getattr(row, "_mapping", row)["name"]: {
                "notnull": int(getattr(row, "_mapping", row)["notnull"]),
                "type": str(getattr(row, "_mapping", row)["type"]),
            }
            for row in rows
        }


    def index_names(db, table_name):
        rows = db.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
        return sorted(getattr(row, "_mapping", row)["name"] for row in rows)


    def index_columns(db, index_name):
        rows = db.execute(text(f"PRAGMA index_info({index_name})")).fetchall()
        return [getattr(row, "_mapping", row)["name"] for row in rows]


    Base.metadata.create_all(bind=current_bind())
    Base.metadata.create_all(bind=current_bind())

    db = backend_app.SessionLocal()
    try:
        inspector = inspect(current_bind())
        route_paths = sorted(route.path for route in backend_app.app.routes)
        columns = table_columns(db, "connector_action_proposals")
        indexes = index_names(db, "connector_action_proposals")
        result = {
            "columns": columns,
            "indexes": indexes,
            "index_columns": {
                "idx_connector_action_actor_status_created": index_columns(
                    db,
                    "idx_connector_action_actor_status_created",
                ),
                "idx_connector_action_type_status": index_columns(
                    db,
                    "idx_connector_action_type_status",
                ),
                "idx_connector_action_target": index_columns(
                    db,
                    "idx_connector_action_target",
                ),
            },
            "model_columns": sorted(ConnectorActionProposal.__table__.columns.keys()),
            "statuses": list(CONNECTOR_ACTION_PROPOSAL_STATUSES),
            "status_default": str(ConnectorActionProposal.__table__.c.status.default.arg),
            "table_names": inspector.get_table_names(),
            "connector_action_routes": [
                path for path in route_paths if "connector" in path and "action" in path
            ],
        }
    finally:
        db.close()

    print("CONNECTOR_ACTION_MODEL_RESULT=" + json.dumps(result, sort_keys=True))
    """
)


class ConnectorActionProposalModelTests(unittest.TestCase):
    def test_connector_action_proposals_table_is_created_idempotently(self):
        result = run_probe(PROBE)

        expected_columns = {
            "id",
            "action_type",
            "actor_user_id",
            "target_type",
            "target_id",
            "draft_payload",
            "status",
            "created_at",
            "approved_at",
            "executed_at",
            "result_payload",
        }
        self.assertIn("connector_action_proposals", result["table_names"])
        self.assertEqual(set(result["columns"]), expected_columns)
        self.assertEqual(set(result["model_columns"]), expected_columns)

    def test_connector_action_proposals_columns_match_contract(self):
        result = run_probe(PROBE)

        required_columns = {
            "action_type",
            "target_type",
            "status",
            "created_at",
        }
        for column_name in required_columns:
            self.assertEqual(result["columns"][column_name]["notnull"], 1)

        nullable_columns = {
            "actor_user_id",
            "target_id",
            "draft_payload",
            "approved_at",
            "executed_at",
            "result_payload",
        }
        for column_name in nullable_columns:
            self.assertEqual(result["columns"][column_name]["notnull"], 0)

        self.assertEqual(
            result["statuses"],
            ["draft", "approved", "executed", "canceled", "failed"],
        )
        self.assertEqual(result["status_default"], "draft")

    def test_connector_action_proposals_indexes_match_contract(self):
        result = run_probe(PROBE)

        self.assertIn("idx_connector_action_actor_status_created", result["indexes"])
        self.assertIn("idx_connector_action_type_status", result["indexes"])
        self.assertIn("idx_connector_action_target", result["indexes"])
        self.assertEqual(
            result["index_columns"]["idx_connector_action_actor_status_created"],
            ["actor_user_id", "status", "created_at"],
        )
        self.assertEqual(
            result["index_columns"]["idx_connector_action_type_status"],
            ["action_type", "status"],
        )
        self.assertEqual(
            result["index_columns"]["idx_connector_action_target"],
            ["target_type", "target_id"],
        )

    def test_connector_action_model_exposes_inbox_cancel_drafts_and_vote_approval(self):
        result = run_probe(PROBE)

        self.assertEqual(
            result["connector_action_routes"],
            [
                "/connector/actions",
                "/connector/actions/draft-ai-delegate-comment",
                "/connector/actions/draft-ai-delegate-review",
                "/connector/actions/draft-ai-review",
                "/connector/actions/draft-collab-request",
                "/connector/actions/draft-comment",
                "/connector/actions/draft-proposal",
                "/connector/actions/draft-vote",
                "/connector/actions/{action_id}/approve-ai-comment",
                "/connector/actions/{action_id}/approve-ai-review",
                "/connector/actions/{action_id}/approve-vote",
                "/connector/actions/{action_id}/cancel",
            ],
        )
        self.assertEqual(
            [
                route
                for route in result["connector_action_routes"]
                if "approve" in route or "execute" in route
            ],
            [
                "/connector/actions/{action_id}/approve-ai-comment",
                "/connector/actions/{action_id}/approve-ai-review",
                "/connector/actions/{action_id}/approve-vote",
            ],
        )


if __name__ == "__main__":
    unittest.main()
