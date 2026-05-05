from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"

FRONTENDS = {
    "next": {
        "dir": ROOT / "frontend-next",
        "env_key": "NEXT_PUBLIC_API_URL",
        "port": 3000,
        "command": ["npm", "run", "dev"],
        "type": "next",
        "status": "legacy",
    },
    "vite-basic": {
        "dir": ROOT / "frontend-vite-basic",
        "env_key": "VITE_API_URL",
        "port": 5174,
        "command": ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5174"],
        "type": "vite",
        "status": "legacy/off-path",
    },
    "vite-3d": {
        "dir": ROOT / "frontend-vite-3d",
        "env_key": "VITE_API_URL",
        "port": 5175,
        "command": ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5175"],
        "type": "vite",
        "status": "legacy/off-path",
    },
    "social-six": {
        "dir": ROOT / "frontend-social-six",
        "env_key": "NEXT_PUBLIC_API_URL",
        "port": 3001,
        "command": ["npm", "run", "dev"],
        "type": "next",
        "status": "legacy/off-path",
    },
    "social-seven": {
        "dir": ROOT / "frontend-social-seven",
        "env_key": "NEXT_PUBLIC_API_URL",
        "port": 3007,
        "command": ["npm", "run", "dev"],
        "type": "next",
        "status": "active/default FE7",
    },
}


def choose_frontend() -> str:
    print("Available frontends:")
    for index, (name, config) in enumerate(FRONTENDS.items(), start=1):
        status = config.get("status")
        status_suffix = f" - {status}" if status else ""
        print(f"  {index}. {name} ({config['dir'].name}){status_suffix}")

    while True:
        raw = input("Select a frontend by number or name: ").strip().lower()
        if raw in FRONTENDS:
            return raw
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(FRONTENDS):
                return list(FRONTENDS.keys())[index]
        print("Invalid selection. Try again.")


def ensure_command_exists(command: str) -> None:
    if resolve_command(command) != command or shutil.which(command):
        return
    raise SystemExit(f"Required command '{command}' was not found in PATH.")


def resolve_command(command: str) -> str:
    if os.name == "nt" and command.lower() == "npm":
        return (
            shutil.which("npm.cmd")
            or shutil.which("npm")
            or r"C:\Program Files\nodejs\npm.cmd"
        )
    return shutil.which(command) or command


def upsert_env_value(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    found = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updated: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            updated.append(f"{key}={value}")
            found = True
        else:
            updated.append(line)

    if not found:
        updated.append(f"{key}={value}")

    env_path.write_text("\n".join(updated).strip() + "\n", encoding="utf-8")


def prepare_frontend_env(frontend_name: str, backend_url: str) -> Path:
    frontend = FRONTENDS[frontend_name]
    env_path = frontend["dir"] / ".env.local"
    upsert_env_value(env_path, frontend["env_key"], backend_url)
    return env_path


def start_process(command: list[str], cwd: Path) -> subprocess.Popen:
    resolved = command[:]
    resolved[0] = resolve_command(resolved[0])
    return subprocess.Popen(resolved, cwd=str(cwd))


def terminate_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the SuperNova backend and a selected frontend locally.")
    parser.add_argument("--frontend", choices=FRONTENDS.keys(), help="Frontend to start.")
    parser.add_argument("--backend-only", action="store_true", help="Start only the backend API.")
    parser.add_argument("--no-backend", action="store_true", help="Start only the selected frontend.")
    parser.add_argument("--backend-port", type=int, default=8000, help="Backend port. Defaults to 8000.")
    parser.add_argument("--list-frontends", action="store_true", help="Print available frontends and exit.")
    args = parser.parse_args()

    if args.list_frontends:
        for name, config in FRONTENDS.items():
            status = config.get("status")
            status_suffix = f" [{status}]" if status else ""
            print(f"{name}: {config['dir']}{status_suffix}")
        return 0

    ensure_command_exists("python")
    ensure_command_exists("npm")

    selected_frontend = None if args.backend_only else (args.frontend or choose_frontend())
    backend_url = f"http://127.0.0.1:{args.backend_port}"

    backend_proc: subprocess.Popen | None = None
    frontend_proc: subprocess.Popen | None = None

    try:
        if not args.no_backend:
            backend_command = [
                sys.executable,
                "-m",
                "uvicorn",
                "app:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(args.backend_port),
            ]
            print(f"Starting backend on {backend_url}")
            backend_proc = start_process(backend_command, ROOT)
            time.sleep(2)

        if selected_frontend:
            env_path = prepare_frontend_env(selected_frontend, backend_url)
            frontend = FRONTENDS[selected_frontend]
            print(f"Prepared {env_path.relative_to(ROOT)} with {frontend['env_key']}={backend_url}")
            print(
                f"Starting frontend '{selected_frontend}' at http://127.0.0.1:{frontend['port']}"
            )
            frontend_proc = start_process(frontend["command"], frontend["dir"])

        if frontend_proc is None and backend_proc is not None:
            return backend_proc.wait()

        while True:
            if backend_proc is not None and backend_proc.poll() is not None:
                return backend_proc.returncode or 0
            if frontend_proc is not None and frontend_proc.poll() is not None:
                return frontend_proc.returncode or 0
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping local stack...")
        return 0
    finally:
        terminate_process(frontend_proc)
        terminate_process(backend_proc)


if __name__ == "__main__":
    raise SystemExit(main())
