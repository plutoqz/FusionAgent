from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


AUDIT_ID = "fusionagent.freeze-c-independent-audit.v1"
REPORT_SCHEMA_VERSION = "1.0.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_freeze_c(
    *,
    evidence_dir: Path,
    manifest_path: Path | None = None,
    worktree: Path | None = None,
    expected_commit: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    evidence_dir = Path(evidence_dir).resolve()
    manifest_path = Path(manifest_path or evidence_dir / "experiment_evidence_manifest.json").resolve()
    checks: list[dict[str, Any]] = []

    if not evidence_dir.is_dir():
        checks.append(_check("evidence_dir", "冻结证据目录存在", [f"目录不存在: {evidence_dir}"], path=str(evidence_dir)))
        return _report(evidence_dir, manifest_path, checks)

    manifest, manifest_error = _load_json_object(manifest_path)
    if manifest_error:
        checks.append(_check("manifest_parse", "manifest 可解析", [manifest_error], path=str(manifest_path)))
        return _report(evidence_dir, manifest_path, checks)

    manifest_hash = sha256_file(manifest_path)
    manifest_errors = []
    if expected_manifest_sha256 and _strip_hash_prefix(expected_manifest_sha256).lower() != manifest_hash:
        manifest_errors.append(
            f"manifest SHA-256 不匹配: expected={_strip_hash_prefix(expected_manifest_sha256)}, actual={manifest_hash}"
        )
    checks.append(
        _check(
            "manifest_hash",
            "manifest SHA-256",
            manifest_errors,
            sha256=manifest_hash,
            expected_sha256=_strip_hash_prefix(expected_manifest_sha256) if expected_manifest_sha256 else None,
            externally_anchored=bool(expected_manifest_sha256),
        )
    )

    package_check = _check_package_hashes(evidence_dir, manifest, manifest_path)
    checks.append(package_check)
    checks.append(_check_external_inputs(manifest))
    checks.append(_check_experiment_result(evidence_dir, manifest_path))
    checks.append(_check_commit_and_worktree(manifest, worktree, expected_commit))

    return _report(evidence_dir, manifest_path, checks, manifest=manifest)


def write_audit_outputs(report: dict[str, Any], report_json: Path, summary_markdown: Path) -> None:
    _write_new_file(Path(report_json), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _write_new_file(Path(summary_markdown), render_summary(report))


def render_summary(report: dict[str, Any]) -> str:
    target = report["target"]
    checks = report["checks"]
    lines = [
        "# Freeze C P1 独立审计摘要",
        "",
        f"- 审计结果：**{'通过' if report['passed'] else '失败'}**",
        f"- 实验：`{target.get('experiment_id') or 'unknown'}`",
        f"- commit：`{target.get('commit_sha') or 'unknown'}`",
        f"- 证据目录：`{target['evidence_dir']}`",
        f"- manifest SHA-256：`{target.get('manifest_sha256') or 'unknown'}`",
        "",
        "## 检查项",
        "",
    ]
    for item in checks:
        lines.append(f"- [{'通过' if item['passed'] else '失败'}] {item['title']} (`{item['id']}`)")
        for error in item.get("errors", []):
            lines.append(f"  - {error}")
    lines.extend(
        [
            "",
            "说明：manifest 自身 SHA-256 已记录；只有命令提供 `--expected-manifest-sha256` 时，才对 manifest 自身做外部信任根比对。",
            "",
        ]
    )
    return "\n".join(lines)


def _check_package_hashes(evidence_dir: Path, manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    declared = manifest.get("files")
    if not isinstance(declared, list):
        return _check("package_hashes", "冻结包文件哈希", ["manifest.files 缺失或不是数组"])

    declared_paths: set[str] = set()
    category_counts: dict[str, int] = {}
    for item in declared:
        if not isinstance(item, dict):
            errors.append("manifest.files 包含非 object 项")
            continue
        relative_path = str(item.get("relative_path") or "")
        safe_path = _safe_relative_path(relative_path)
        if safe_path is None:
            errors.append(f"非法相对路径: {relative_path}")
            continue
        declared_paths.add(safe_path)
        category = _package_category(safe_path)
        category_counts[category] = category_counts.get(category, 0) + 1
        target = evidence_dir / safe_path
        if not target.is_file():
            errors.append(f"{safe_path}: missing")
            continue
        expected_hash = str(item.get("sha256") or "")
        expected_size = item.get("size_bytes")
        actual_hash = sha256_file(target)
        if actual_hash != _strip_hash_prefix(expected_hash):
            errors.append(f"{safe_path}: hash changed")
        if target.stat().st_size != expected_size:
            errors.append(f"{safe_path}: size changed")

    actual_paths = {
        path.relative_to(evidence_dir).as_posix()
        for path in evidence_dir.rglob("*")
        if path.is_file()
    }
    manifest_relative = _relative_to(evidence_dir, manifest_path)
    allowed_paths = set(declared_paths)
    if manifest_relative is not None:
        allowed_paths.add(manifest_relative)
    for extra in sorted(actual_paths - allowed_paths):
        errors.append(f"unexpected file: {extra}")
    for missing in sorted(declared_paths - actual_paths):
        errors.append(f"missing declared file: {missing}")

    required_categories = {"prepared_input", "runtime_input", "runtime_output", "raw_package"}
    missing_categories = sorted(required_categories - set(category_counts))
    if missing_categories:
        errors.append(f"冻结包缺少受保护类别: {', '.join(missing_categories)}")
    return _check(
        "package_hashes",
        "冻结包逐文件 SHA-256 与 clean 文件集",
        errors,
        declared_file_count=len(declared_paths),
        actual_file_count=len(actual_paths),
        category_counts=category_counts,
        allowed_manifest_path=manifest_relative,
    )


def _check_external_inputs(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    sources = manifest.get("external_inputs")
    if not isinstance(sources, list):
        return _check("external_input_hashes", "原始外部输入逐文件 SHA-256", ["manifest.external_inputs 缺失或不是数组"])
    file_count = 0
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("files"), list):
            errors.append("external_inputs 包含缺少 files 数组的项")
            continue
        for item in source["files"]:
            file_count += 1
            if not isinstance(item, dict):
                errors.append("external_inputs.files 包含非 object 项")
                continue
            raw_path = str(item.get("path") or "")
            target = Path(raw_path)
            if not target.is_file():
                errors.append(f"{raw_path}: missing")
                continue
            if sha256_file(target) != _strip_hash_prefix(str(item.get("sha256") or "")):
                errors.append(f"{raw_path}: hash changed")
            if target.stat().st_size != item.get("size_bytes"):
                errors.append(f"{raw_path}: size changed")
    return _check(
        "external_input_hashes",
        "原始外部输入逐文件 SHA-256",
        errors,
        source_count=len(sources),
        file_count=file_count,
    )


def _check_experiment_result(evidence_dir: Path, manifest_path: Path) -> dict[str, Any]:
    result_path = evidence_dir / "experiment_result.json"
    result, error = _load_json_object(result_path)
    if error:
        return _check("experiment_result", "实验结果与 all_cases_passed 闸门", [error])
    errors: list[str] = []
    if result.get("all_cases_passed") is not True:
        errors.append("experiment_result.all_cases_passed 必须为 true")
    case_results = result.get("case_results")
    if not isinstance(case_results, list) or not case_results:
        errors.append("experiment_result.case_results 必须是非空数组")
        case_results = []
    failed_cases = [str(item.get("case_id")) for item in case_results if not isinstance(item, dict) or item.get("passed") is not True]
    if failed_cases:
        errors.append(f"失败案例: {', '.join(failed_cases)}")
    recorded_manifest = result.get("evidence_manifest_path")
    if recorded_manifest:
        try:
            if Path(str(recorded_manifest)).resolve() != manifest_path.resolve():
                errors.append("experiment_result.evidence_manifest_path 未指向当前 manifest")
        except OSError:
            errors.append("experiment_result.evidence_manifest_path 无法解析")
    return _check(
        "experiment_result",
        "实验结果与 all_cases_passed 闸门",
        errors,
        case_count=len(case_results),
        failed_cases=failed_cases,
        all_cases_passed=result.get("all_cases_passed"),
    )


def _check_commit_and_worktree(
    manifest: dict[str, Any], worktree: Path | None, expected_commit: str | None
) -> dict[str, Any]:
    errors: list[str] = []
    manifest_commit = str(manifest.get("commit_sha") or "")
    if not manifest_commit:
        errors.append("manifest.commit_sha 缺失")
    if expected_commit and manifest_commit != expected_commit:
        errors.append(f"manifest.commit_sha 不匹配: expected={expected_commit}, actual={manifest_commit}")
    details: dict[str, Any] = {"manifest_commit": manifest_commit, "expected_commit": expected_commit}
    if worktree is not None:
        worktree = Path(worktree).resolve()
        try:
            actual_commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=worktree, text=True, stderr=subprocess.STDOUT
            ).strip()
            status = subprocess.check_output(
                ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
                cwd=worktree,
                text=True,
                stderr=subprocess.STDOUT,
            )
            details.update({"worktree": str(worktree), "actual_commit": actual_commit, "status_porcelain": status.splitlines()})
            if actual_commit != manifest_commit:
                errors.append(f"worktree HEAD 不匹配: expected={manifest_commit}, actual={actual_commit}")
            if status.strip():
                errors.append("Freeze C worktree 不是 clean")
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"无法读取 git worktree: {exc}")
    return _check("commit_and_clean_worktree", "commit 与冻结 worktree clean 状态", errors, **details)


def _package_category(relative_path: str) -> str:
    name = Path(relative_path).name
    if name.startswith("prepared_inputs_"):
        return "prepared_input"
    if "/input/" in f"/{relative_path}":
        return "runtime_input"
    if "/output/" in f"/{relative_path}":
        return "runtime_output"
    if relative_path.startswith("runtime/data_repository/") or relative_path.startswith("runtime/downloads/"):
        return "raw_package"
    if relative_path.startswith("cases/"):
        return "case_evidence"
    return "metadata"


def _report(
    evidence_dir: Path,
    manifest_path: Path,
    checks: list[dict[str, Any]],
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_hash = sha256_file(manifest_path) if manifest_path.is_file() else None
    return {
        "audit_id": AUDIT_ID,
        "schema_version": REPORT_SCHEMA_VERSION,
        "passed": all(item["passed"] for item in checks),
        "target": {
            "evidence_dir": str(evidence_dir),
            "manifest_path": str(manifest_path),
            "manifest_sha256": manifest_hash,
            "experiment_id": (manifest or {}).get("experiment_id"),
            "commit_sha": (manifest or {}).get("commit_sha"),
        },
        "checks": checks,
    }


def _check(check_id: str, title: str, errors: Iterable[str], **details: Any) -> dict[str, Any]:
    normalized = list(dict.fromkeys(str(error) for error in errors if str(error)))
    return {"id": check_id, "title": title, "passed": not normalized, "errors": normalized, "details": details}


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"文件不存在: {path}"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"无法解析 {path}: {exc}"
    if not isinstance(payload, dict):
        return None, f"顶层必须是 JSON object: {path}"
    return payload, None


def _safe_relative_path(value: str) -> str | None:
    path = Path(value.replace("\\", "/"))
    if not value or path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def _relative_to(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _strip_hash_prefix(value: str) -> str:
    return (value[7:] if value.lower().startswith("sha256:") else value).lower()


def _write_new_file(path: Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="独立审计 Freeze C 证据包，不导入 FusionAgent 运行模块。")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--manifest", default="")
    parser.add_argument("--worktree", default="")
    parser.add_argument("--expected-commit", default="")
    parser.add_argument("--expected-manifest-sha256", default="")
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--summary-markdown", required=True)
    args = parser.parse_args(argv)
    report = audit_freeze_c(
        evidence_dir=Path(args.evidence_dir),
        manifest_path=Path(args.manifest) if args.manifest else None,
        worktree=Path(args.worktree) if args.worktree else None,
        expected_commit=args.expected_commit or None,
        expected_manifest_sha256=args.expected_manifest_sha256 or None,
    )
    try:
        write_audit_outputs(report, Path(args.report_json), Path(args.summary_markdown))
    except FileExistsError as exc:
        print(f"拒绝覆盖已有审计输出: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
