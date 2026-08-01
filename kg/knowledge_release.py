from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_RELEASE_DIR = Path(__file__).resolve().parent / "ontology" / "v1.0.0"
DEFAULT_RELEASE_PATH = DEFAULT_RELEASE_DIR / "release.json"
DEFAULT_SCHEMA_PATH = DEFAULT_RELEASE_DIR / "schema.json"
DEFAULT_ENTITIES_PATH = DEFAULT_RELEASE_DIR / "entities.json"
DEFAULT_POLICIES_PATH = DEFAULT_RELEASE_DIR / "policies.json"


class KnowledgeReleaseError(RuntimeError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def semantic_hash(*payloads: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(list(payloads))).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeReleaseError(f"Cannot read KG release file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KnowledgeReleaseError(f"KG release file must contain a JSON object: {path}")
    return payload


@lru_cache(maxsize=4)
def load_release_index(path: Path = DEFAULT_RELEASE_PATH, *, verify: bool = True) -> dict[str, Any]:
    release_path = Path(path).resolve()
    payload = _load_json(release_path)
    if payload.get("status") != "frozen":
        raise KnowledgeReleaseError(f"KG release is not frozen: {release_path}")
    if verify:
        verify_release(release_path.parent, release_payload=payload)
    return payload


def verify_release(release_dir: Path = DEFAULT_RELEASE_DIR, *, release_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(release_dir).resolve()
    release = release_payload or _load_json(root / "release.json")
    failures: list[str] = []
    files = release.get("files")
    if not isinstance(files, dict) or not files:
        failures.append("release.files is missing")
        files = {}
    for relative_path, expected_hash in sorted(files.items()):
        target = (root / str(relative_path)).resolve()
        if target.parent != root:
            failures.append(f"release file escapes directory: {relative_path}")
            continue
        if not target.is_file():
            failures.append(f"release file missing: {relative_path}")
            continue
        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            failures.append(f"hash mismatch for {relative_path}: expected {expected_hash}, got {actual_hash}")

    if not failures:
        schema = _load_json(root / "schema.json")
        entities = _load_json(root / "entities.json")
        policies = _load_json(root / "policies.json")
        actual_semantic_hash = semantic_hash(schema, entities, policies)
        if actual_semantic_hash != release.get("semantic_hash"):
            failures.append(
                f"semantic hash mismatch: expected {release.get('semantic_hash')}, got {actual_semantic_hash}"
            )

    if failures:
        raise KnowledgeReleaseError("; ".join(failures))
    return release


@lru_cache(maxsize=4)
def load_policies(path: Path = DEFAULT_POLICIES_PATH, *, verify_release_files: bool = True) -> dict[str, Any]:
    policy_path = Path(path).resolve()
    if verify_release_files and policy_path == DEFAULT_POLICIES_PATH.resolve():
        load_release_index()
    return _load_json(policy_path)


def get_knowledge_identity() -> dict[str, str]:
    release = load_release_index()
    return {
        "release_id": str(release["release_id"]),
        "ontology_version": str(release["ontology_version"]),
        "knowledge_version": str(release["knowledge_version"]),
        "semantic_hash": str(release["semantic_hash"]),
        "experience_snapshot_hash": str(release["experience_snapshot_hash"]),
    }


def clear_release_caches() -> None:
    load_release_index.cache_clear()
    load_policies.cache_clear()
