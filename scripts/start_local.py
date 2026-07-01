from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.bootstrap import prepare_local_neo4j
from utils.local_runtime import (
    DEFAULT_DEPENDENCY_FILE,
    DependencyConfigError,
    build_local_runtime_env_defaults,
    find_missing_runtime_dependencies,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start FusionAgent locally with Redis/Neo4j/LLM defaults.")
    parser.add_argument("--mode", choices=["fast", "full"], default="full", help="Runtime profile to validate/start.")
    parser.add_argument("--port", type=int, default=8000, help="API port.")
    parser.add_argument("--auto-port", action="store_true", help="Switch to the next free port if the requested port is occupied.")
    parser.add_argument("--install-deps", action="store_true", help="Install missing Python dependencies automatically.")
    parser.add_argument("--check-only", action="store_true", help="Only validate dependencies and bootstrap Neo4j.")
    parser.add_argument("--runs-root", type=Path, default=None, help="Use a custom runs root for this runtime.")
    parser.add_argument("--redis-db", type=int, default=None, help="Override the Redis DB number used by Celery.")
    parser.add_argument(
        "--isolated-run-id",
        default=None,
        help="Create an isolated runtime under tmp/isolated-runtime/<id> with a dedicated runs root.",
    )
    parser.add_argument("--disable-recovery", action="store_true", help="Disable recovery_tick for this runtime.")
    parser.add_argument("--disable-scheduler", action="store_true", help="Do not start Celery beat for this runtime.")
    parser.add_argument(
        "--reset-managed-graph",
        action="store_true",
        help="Delete only FusionAgent-managed Neo4j nodes before reseeding.",
    )
    return parser


def _install_dependencies() -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt")], cwd=REPO_ROOT)


def _redis_url_with_db(url: str, redis_db: int) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"redis", "rediss"}:
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{int(redis_db)}", parsed.query, parsed.fragment))


def _build_env(
    port: int,
    *,
    mode: str = "full",
    runs_root: Path | None = None,
    redis_db: int | None = None,
    disable_recovery: bool = False,
    disable_scheduler: bool = False,
) -> dict[str, str]:
    applied = build_local_runtime_env_defaults(
        mode=mode,
        require_dependency_file=str(mode).strip().lower() == "full",
    )
    env = os.environ.copy()
    for key, value in applied.items():
        env.setdefault(key, value)
    env.setdefault("GEOFUSION_TIMEZONE", env.get("TZ", "Asia/Shanghai"))
    env.setdefault("GEOFUSION_LLM_MODEL", applied.get("GEOFUSION_LLM_MODEL", "qwen3.5-397b-a17b"))
    if runs_root is not None:
        env["GEOFUSION_RUNS_ROOT"] = str(Path(runs_root))
    if redis_db is not None:
        broker = env.get("GEOFUSION_CELERY_BROKER", "redis://localhost:6379/0")
        backend = env.get("GEOFUSION_CELERY_BACKEND", broker)
        env["GEOFUSION_CELERY_BROKER"] = _redis_url_with_db(broker, redis_db)
        env["GEOFUSION_CELERY_BACKEND"] = _redis_url_with_db(backend, redis_db)
    if disable_recovery:
        env["GEOFUSION_RECOVERY_ENABLED"] = "0"
    if disable_scheduler:
        env["GEOFUSION_SCHEDULER_ENABLED"] = "0"
    env["GEOFUSION_API_PORT"] = str(port)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _diagnostic_error(code: str, message: str, **details: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": False,
        "code": code,
        "message": message,
    }
    payload.update(details)
    return payload


def _print_diagnostic(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _port_is_open(port: int, *, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((host, int(port))) == 0


def _probe_runtime_identity(port: int) -> dict[str, object]:
    if not _port_is_open(port):
        return {"state": "free", "port": port}
    url = f"http://127.0.0.1:{port}/api/v2/runtime"
    try:
        request = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(request, timeout=1.0) as response:
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body) if body.strip() else {}
            if response.status == 200 and isinstance(payload, dict) and "kg_backend" in payload:
                return {"state": "fusionagent", "port": port, "url": url, "runtime": payload}
            return {"state": "conflict", "port": port, "url": url, "status": response.status, "body": body[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"state": "conflict", "port": port, "url": url, "error": f"{type(exc).__name__}: {exc}"}


def _next_available_port(start_port: int) -> int:
    port = int(start_port)
    while _port_is_open(port):
        port += 1
    return port


def _resolve_start_port(requested_port: int, *, auto_port: bool) -> int:
    identity = _probe_runtime_identity(requested_port)
    if identity["state"] == "free":
        return requested_port
    if identity["state"] == "fusionagent":
        raise RuntimeError(
            "PORT_CONFLICT: FusionAgent already appears to be running on "
            f"http://127.0.0.1:{requested_port}. Stop it or pass --port/--auto-port."
        )
    if auto_port:
        port = _next_available_port(requested_port + 1)
        print(f"Port {requested_port} is occupied by a non-FusionAgent service; using {port}.")
        return port
    raise RuntimeError(
        "PORT_CONFLICT: requested port is occupied by a non-FusionAgent service. "
        f"Probe={identity}. Pass --auto-port or choose --port {requested_port + 1}."
    )


def _isolated_runs_root(run_id: str) -> Path:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in run_id).strip("-_")
    safe = safe or f"runtime-{int(time.time())}"
    return REPO_ROOT / "tmp" / "isolated-runtime" / safe / "runs"


def _prepare_neo4j(env: dict[str, str], *, reset_managed_graph: bool = False) -> dict[str, object]:
    if env.get("GEOFUSION_KG_BACKEND", "neo4j").strip().lower() == "memory":
        return {
            "edition": None,
            "isolation_mode": "memory",
            "database_used": None,
            "notes": [],
            "bootstrap_applied": False,
            "expected_seed_inventory": {},
            "missing_seed_labels": {},
            "kg_contract_ok": True,
            "managed_nodes_deleted": 0,
            "managed_inventory": {"label_counts": [], "relationship_counts": [], "node_count": 0},
            "foreign_labels": [],
        }

    summary = prepare_local_neo4j(
        uri=env["GEOFUSION_NEO4J_URI"],
        user=env["GEOFUSION_NEO4J_USER"],
        password=env["GEOFUSION_NEO4J_PASSWORD"],
        database=env.get("GEOFUSION_NEO4J_DATABASE") or None,
        reset_managed=reset_managed_graph,
    )
    database_used = summary.get("database_used")
    if database_used:
        env["GEOFUSION_NEO4J_DATABASE"] = str(database_used)
    else:
        env.pop("GEOFUSION_NEO4J_DATABASE", None)
    return summary


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
    mode = str(args.mode or "full").strip().lower()

    missing = find_missing_runtime_dependencies()
    if missing:
        if not args.install_deps:
            print("Missing Python dependencies:", ", ".join(missing))
            print(f"Run: {sys.executable} -m pip install -r requirements.txt")
            return 1
        _install_dependencies()

    runs_root = args.runs_root
    disable_recovery = args.disable_recovery
    disable_scheduler = args.disable_scheduler
    redis_db = args.redis_db
    if args.isolated_run_id:
        runs_root = runs_root or _isolated_runs_root(args.isolated_run_id)
        disable_recovery = True if not args.disable_recovery else args.disable_recovery
        disable_scheduler = True if not args.disable_scheduler else args.disable_scheduler
        redis_db = 7 if redis_db is None else redis_db

    try:
        env = _build_env(
            args.port,
            mode=mode,
            runs_root=runs_root,
            redis_db=redis_db,
            disable_recovery=disable_recovery,
            disable_scheduler=disable_scheduler,
        )
    except DependencyConfigError as exc:
        _print_diagnostic(
            _diagnostic_error(
                "CONFIG_MISSING",
                str(exc),
                mode=mode,
                missing_file=str(DEFAULT_DEPENDENCY_FILE),
                example_file=str(REPO_ROOT / "依赖.txt.example"),
                next_action=(
                    "Copy 依赖.txt.example to 依赖.txt and fill Redis/Neo4j/LLM values, "
                    "or use --mode fast for memory/mock/eager local checks."
                ),
            )
        )
        return 1

    try:
        port = _resolve_start_port(args.port, auto_port=args.auto_port or mode == "fast")
    except RuntimeError as exc:
        _print_diagnostic(
            _diagnostic_error(
                "PORT_CONFLICT",
                str(exc),
                requested_port=args.port,
                next_action=f"Stop the service on port {args.port}, pass --auto-port, or choose --port {args.port + 1}.",
            )
        )
        return 1
    env["GEOFUSION_API_PORT"] = str(port)

    try:
        neo4j_summary = _prepare_neo4j(env, reset_managed_graph=args.reset_managed_graph)
    except Exception as exc:  # noqa: BLE001
        _print_diagnostic(
            _diagnostic_error(
                "CONFIG_MISSING" if mode == "full" else "RUNTIME_PRECHECK_FAILED",
                f"{type(exc).__name__}: {exc}",
                mode=mode,
                next_action="Run scripts/windows_runtime_doctor.py or switch to --mode fast for local mock execution.",
            )
        )
        return 1
    if neo4j_summary["isolation_mode"] != "memory":
        print(f"Neo4j edition: {neo4j_summary['edition']}")
        print(f"Neo4j isolation: {neo4j_summary['isolation_mode']}")
        if neo4j_summary.get("database_used"):
            print(f"Neo4j database: {neo4j_summary['database_used']}")
        if neo4j_summary.get("graph_namespace"):
            print(f"Neo4j namespace guard: {neo4j_summary['graph_namespace']}")
        print(f"Neo4j bootstrap: {'applied' if neo4j_summary['bootstrap_applied'] else 'already seeded'}")
        if neo4j_summary.get("managed_nodes_deleted"):
            print(f"Neo4j managed cleanup: deleted {neo4j_summary['managed_nodes_deleted']} nodes")
        if neo4j_summary.get("kg_contract_ok", False):
            print("KG contract: PASS")
        else:
            print(f"KG contract: FAIL missing={neo4j_summary.get('missing_seed_labels', {})}")
        notes = neo4j_summary.get("notes") or []
        for note in notes:
            print(f"Neo4j note: {note}")
        foreign_labels = neo4j_summary.get("foreign_labels") or []
        if foreign_labels:
            preview = ", ".join(f"{item['label']}({item['count']})" for item in foreign_labels[:6])
            print(f"Neo4j foreign labels detected outside FusionAgent-managed graph: {preview}")
        if not neo4j_summary.get("kg_contract_ok", False):
            raise RuntimeError("Neo4j managed graph does not satisfy the FusionAgent KG contract.")

    if args.check_only:
        print(f"Local runtime check passed. mode={mode} port={port}")
        return 0

    runtime_runs_root = Path(env.get("GEOFUSION_RUNS_ROOT", REPO_ROOT / "runs"))
    log_dir = runtime_runs_root / "local-runtime"
    processes = {
        "api": _start_process(
            "api",
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)],
            env,
            log_dir,
        ),
        "worker": _start_process(
            "worker",
            _worker_command(),
            env,
            log_dir,
        ),
    }
    if env.get("GEOFUSION_SCHEDULER_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}:
        processes["scheduler"] = _start_process(
            "scheduler",
            [sys.executable, "-m", "celery", "-A", "worker.celery_app.celery_app", "beat", "-l", "info"],
            env,
            log_dir,
        )
    _assert_processes_started(processes, log_dir)

    print(f"API: http://127.0.0.1:{port}")
    print(f"runs root: {runtime_runs_root}")
    print(f"celery broker: {env.get('GEOFUSION_CELERY_BROKER')}")
    if env.get("GEOFUSION_RECOVERY_ENABLED") == "0":
        print("recovery: disabled")
    if env.get("GEOFUSION_SCHEDULER_ENABLED") == "0":
        print("scheduler: disabled")
    for name, process in processes.items():
        print(f"{name}: pid={process.pid} log={log_dir / f'{name}.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
