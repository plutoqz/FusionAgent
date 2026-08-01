from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.start_local import _probe_runtime_identity
from utils.local_runtime import DEFAULT_DEPENDENCY_FILE, build_local_runtime_env_defaults, find_missing_runtime_dependencies


def build_runtime_doctor_report(*, mode: str, port: int) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    checks["python"] = {"ok": True, "executable": sys.executable, "version": sys.version.split()[0]}
    missing = find_missing_runtime_dependencies()
    checks["python_dependencies"] = {"ok": not missing, "missing": missing}
    checks["dependency_file"] = {
        "ok": mode == "fast" or DEFAULT_DEPENDENCY_FILE.exists(),
        "path": str(DEFAULT_DEPENDENCY_FILE),
        "required": mode == "full",
    }
    try:
        env_defaults = build_local_runtime_env_defaults(
            mode=mode,
            require_dependency_file=mode == "full",
        )
        checks["runtime_config"] = {
            "ok": True,
            "kg_backend": env_defaults.get("GEOFUSION_KG_BACKEND"),
            "llm_provider": env_defaults.get("GEOFUSION_LLM_PROVIDER"),
            "celery_eager": env_defaults.get("GEOFUSION_CELERY_EAGER"),
        }
    except Exception as exc:  # noqa: BLE001
        checks["runtime_config"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    checks["port"] = _probe_runtime_identity(port)

    writable = {}
    for path in (REPO_ROOT / "runs", REPO_ROOT / "tmp"):
        try:
            path.mkdir(parents=True, exist_ok=True)
            marker = path / ".runtime-doctor-write-test"
            marker.write_text("ok", encoding="utf-8")
            marker.unlink(missing_ok=True)
            writable[str(path)] = {"ok": True}
        except Exception as exc:  # noqa: BLE001
            writable[str(path)] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    checks["write_permissions"] = writable

    ok = all(
        bool(value.get("ok", value.get("state") in {"free", "fusionagent"}))
        for value in checks.values()
        if isinstance(value, dict)
    )
    return {
        "status": "ready" if ok else "blocked",
        "mode": mode,
        "repo_root": str(REPO_ROOT),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check FusionAgent runtime dependencies and local service identity.")
    parser.add_argument("--mode", choices=["fast", "full"], default="fast")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    report = build_runtime_doctor_report(mode=args.mode, port=args.port)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
