from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.bootstrap import ensure_bootstrap_data
from utils.local_runtime import apply_local_dependency_defaults, find_missing_runtime_dependencies


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start GeoFusion locally with real Redis/Neo4j/LLM defaults.")
    parser.add_argument("--port", type=int, default=8000, help="API port.")
    parser.add_argument("--install-deps", action="store_true", help="Install missing Python dependencies automatically.")
    parser.add_argument("--check-only", action="store_true", help="Only validate dependencies and bootstrap Neo4j.")
    return parser


def _install_dependencies() -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt")], cwd=REPO_ROOT)


def _build_env(port: int) -> dict[str, str]:
    applied = apply_local_dependency_defaults(required=True)
    env = os.environ.copy()
    env.setdefault("GEOFUSION_CELERY_EAGER", "0")
    env.setdefault("GEOFUSION_TIMEZONE", env.get("TZ", "Asia/Shanghai"))
    env.setdefault("GEOFUSION_KG_BACKEND", "neo4j")
    env.setdefault("GEOFUSION_LLM_PROVIDER", "openai")
    env.setdefault("GEOFUSION_LLM_MODEL", applied.get("GEOFUSION_LLM_MODEL", "qwen3.5-397b-a17b"))
    env["GEOFUSION_API_PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _ensure_bootstrap(env: dict[str, str]) -> bool:
    if env.get("GEOFUSION_KG_BACKEND", "neo4j").strip().lower() == "memory":
        return False
    return ensure_bootstrap_data(
        uri=env["GEOFUSION_NEO4J_URI"],
        user=env["GEOFUSION_NEO4J_USER"],
        password=env["GEOFUSION_NEO4J_PASSWORD"],
        database=env.get("GEOFUSION_NEO4J_DATABASE") or None,
    )


def _start_process(name: str, command: list[str], env: dict[str, str], log_dir: Path) -> subprocess.Popen:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}.log"
    log_handle = log_path.open("ab")
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    setattr(process, "_log_handle", log_handle)
    return process


def _assert_processes_started(processes: dict[str, subprocess.Popen], log_dir: Path) -> None:
    time.sleep(3.0)
    failures: list[str] = []
    for name, process in processes.items():
        if process.poll() is None:
            continue
        log_path = log_dir / f"{name}.log"
        tail = ""
        if log_path.exists():
            tail = "\n".join(log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[-20:])
        failures.append(f"{name} exited early with code {process.returncode}\n{tail}")
    if failures:
        raise RuntimeError("\n\n".join(failures))


def _worker_command() -> list[str]:
    command = [sys.executable, "-m", "celery", "-A", "worker.celery_app.celery_app", "worker", "-l", "info"]
    if os.name == "nt":
        command.extend(["--pool", "solo", "--concurrency", "1"])
    return command


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    missing = find_missing_runtime_dependencies()
    if missing:
        if not args.install_deps:
            print("Missing Python dependencies:", ", ".join(missing))
            print(f"Run: {sys.executable} -m pip install -r requirements.txt")
            return 1
        _install_dependencies()

    env = _build_env(args.port)
    changed = _ensure_bootstrap(env)
    print(f"Neo4j bootstrap: {'applied' if changed else 'already seeded'}")

    if args.check_only:
        print("Local runtime check passed.")
        return 0

    log_dir = REPO_ROOT / "runs" / "local-runtime"
    processes = {
        "api": _start_process(
            "api",
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(args.port)],
            env,
            log_dir,
        ),
        "worker": _start_process(
            "worker",
            _worker_command(),
            env,
            log_dir,
        ),
        "scheduler": _start_process(
            "scheduler",
            [sys.executable, "-m", "celery", "-A", "worker.celery_app.celery_app", "beat", "-l", "info"],
            env,
            log_dir,
        ),
    }
    _assert_processes_started(processes, log_dir)

    print(f"API: http://127.0.0.1:{args.port}")
    for name, process in processes.items():
        print(f"{name}: pid={process.pid} log={log_dir / f'{name}.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
