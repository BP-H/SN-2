import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_rate_probe(probe: str, env_overrides: dict[str, str] | None = None) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "rate_limits.sqlite"
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "DB_MODE": "central",
                "SECRET_KEY": "strong-test-secret-for-commons-rate-limits",
                "SUPERNOVA_ENV": "development",
                "APP_ENV": "development",
                "ENV": "development",
                "UPLOADS_DIR": str(Path(tmpdir) / "uploads"),
                "FOLLOWS_STORE_PATH": str(Path(tmpdir) / "follows_store.json"),
            }
        )
        if env_overrides:
            env.update(env_overrides)
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

    if completed.returncode != 0:
        raise AssertionError(
            f"probe failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    result_lines = [
        line
        for line in completed.stdout.splitlines()
        if line.startswith("RATE_LIMIT_RESULT=")
    ]
    if not result_lines:
        raise AssertionError(f"probe result missing\nstdout:\n{completed.stdout}")
    return json.loads(result_lines[-1].split("=", 1)[1])


PROBE_PREAMBLE = """
import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

project_root = Path.cwd()
backend_dir = project_root / "backend"
for path in (project_root, backend_dir):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

import backend.app as backend_app

client = TestClient(backend_app.app)
backend_app._reset_rate_limit_state_for_tests()

def response_payload(response):
    try:
        body = response.json()
    except Exception:
        body = {}
    return {
        "status": response.status_code,
        "body": body,
        "retry_after": response.headers.get("retry-after"),
        "bucket": response.headers.get("x-supernova-ratelimit-bucket"),
    }
"""


class CommonsRateLimitTests(unittest.TestCase):
    def test_auth_bucket_returns_friendly_429_and_status_is_exempt(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            first = response_payload(client.post("/auth/login", json={}))
            second = response_payload(client.post("/auth/login", json={}))
            status_hits = [response_payload(client.get("/supernova-status")) for _ in range(3)]
            print("RATE_LIMIT_RESULT=" + json.dumps({
                "first": first,
                "second": second,
                "status_hits": status_hits,
            }, sort_keys=True))
            """
        )
        result = run_rate_probe(
            probe,
            {
                "SUPERNOVA_RATE_LIMIT_ENABLED": "true",
                "SUPERNOVA_RATE_LIMIT_AUTH_PER_MINUTE": "1",
                "SUPERNOVA_RATE_LIMIT_PUBLIC_READS_PER_MINUTE": "1",
            },
        )

        self.assertNotEqual(result["first"]["status"], 429)
        self.assertEqual(result["second"]["status"], 429)
        self.assertEqual(result["second"]["body"]["error_code"], "rate_limited")
        self.assertEqual(result["second"]["body"]["bucket"], "auth")
        self.assertIn("commons stays reachable", result["second"]["body"]["detail"])
        self.assertTrue(result["second"]["retry_after"])
        self.assertTrue(all(hit["status"] != 429 for hit in result["status_hits"]))

    def test_ai_upload_and_write_buckets_are_route_specific(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            ai_first = response_payload(client.post("/connector/actions/draft-ai-delegate-comment", json={}))
            ai_second = response_payload(client.post("/connector/actions/draft-ai-delegate-comment", json={}))
            backend_app._reset_rate_limit_state_for_tests()
            upload_first = response_payload(client.post("/upload-image", json={}))
            upload_second = response_payload(client.post("/upload-image", json={}))
            backend_app._reset_rate_limit_state_for_tests()
            write_first = response_payload(client.post("/comments", json={}))
            write_second = response_payload(client.post("/comments", json={}))
            print("RATE_LIMIT_RESULT=" + json.dumps({
                "ai_first": ai_first,
                "ai_second": ai_second,
                "upload_first": upload_first,
                "upload_second": upload_second,
                "write_first": write_first,
                "write_second": write_second,
            }, sort_keys=True))
            """
        )
        result = run_rate_probe(
            probe,
            {
                "SUPERNOVA_RATE_LIMIT_ENABLED": "true",
                "SUPERNOVA_RATE_LIMIT_AI_GENERATION_PER_MINUTE": "1",
                "SUPERNOVA_RATE_LIMIT_UPLOADS_PER_HOUR": "1",
                "SUPERNOVA_RATE_LIMIT_WRITES_PER_MINUTE": "1",
            },
        )

        self.assertNotEqual(result["ai_first"]["status"], 429)
        self.assertEqual(result["ai_second"]["status"], 429)
        self.assertEqual(result["ai_second"]["body"]["bucket"], "ai_generation")
        self.assertNotEqual(result["upload_first"]["status"], 429)
        self.assertEqual(result["upload_second"]["status"], 429)
        self.assertEqual(result["upload_second"]["body"]["bucket"], "uploads")
        self.assertNotEqual(result["write_first"]["status"], 429)
        self.assertEqual(result["write_second"]["status"], 429)
        self.assertEqual(result["write_second"]["body"]["bucket"], "writes")

    def test_authenticated_user_keying_is_separate_and_switch_can_disable(self):
        probe = PROBE_PREAMBLE + textwrap.dedent(
            """
            alice = backend_app._create_wrapper_access_token("alice", user_id=1)
            bob = backend_app._create_wrapper_access_token("bob", user_id=2)
            headers_alice = {"Authorization": f"Bearer {alice}"}
            headers_bob = {"Authorization": f"Bearer {bob}"}
            alice_first = response_payload(client.post("/connector/actions/draft-ai-delegate-review", json={}, headers=headers_alice))
            alice_second = response_payload(client.post("/connector/actions/draft-ai-delegate-review", json={}, headers=headers_alice))
            bob_first = response_payload(client.post("/connector/actions/draft-ai-delegate-review", json={}, headers=headers_bob))
            os.environ["SUPERNOVA_RATE_LIMIT_ENABLED"] = "false"
            backend_app._reset_rate_limit_state_for_tests()
            disabled_first = response_payload(client.post("/auth/login", json={}))
            disabled_second = response_payload(client.post("/auth/login", json={}))
            print("RATE_LIMIT_RESULT=" + json.dumps({
                "alice_first": alice_first,
                "alice_second": alice_second,
                "bob_first": bob_first,
                "disabled_first": disabled_first,
                "disabled_second": disabled_second,
            }, sort_keys=True))
            """
        )
        result = run_rate_probe(
            probe,
            {
                "SUPERNOVA_RATE_LIMIT_ENABLED": "true",
                "SUPERNOVA_RATE_LIMIT_AI_GENERATION_PER_MINUTE": "1",
                "SUPERNOVA_RATE_LIMIT_AUTH_PER_MINUTE": "1",
            },
        )

        self.assertNotEqual(result["alice_first"]["status"], 429)
        self.assertEqual(result["alice_second"]["status"], 429)
        self.assertNotEqual(result["bob_first"]["status"], 429)
        self.assertNotEqual(result["disabled_first"]["status"], 429)
        self.assertNotEqual(result["disabled_second"]["status"], 429)


if __name__ == "__main__":
    unittest.main()
