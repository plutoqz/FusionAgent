from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kg.knowledge_release import semantic_hash, sha256_file
from kg.seed_manifest import seal_manifest_payload


def build_release(release_dir: Path) -> dict[str, object]:
    release_dir = Path(release_dir)
    schema_path = release_dir / "schema.json"
    entities_path = release_dir / "entities.json"
    policies_path = release_dir / "policies.json"
    if not schema_path.is_file() or not entities_path.is_file() or not policies_path.is_file():
        raise FileNotFoundError("schema.json, entities.json and policies.json must exist before sealing a KG release")

    entities = json.loads(entities_path.read_text(encoding="utf-8"))
    entities = seal_manifest_payload(entities)
    entities_path.write_text(json.dumps(entities, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    schema_metadata = schema.get("metadata") or {}
    entity_metadata = entities.get("metadata") or {}
    policy_metadata = policies.get("metadata") or {}
    release_id = str(entity_metadata.get("release_id") or "")
    ontology_version = str(schema_metadata.get("ontology_version") or "")
    knowledge_version = str(entity_metadata.get("knowledge_version") or "")
    if not release_id or not ontology_version or not knowledge_version:
        raise ValueError("KG release identity is incomplete in schema/entities metadata")
    if schema_metadata.get("release_id") != release_id or policy_metadata.get("release_id") != release_id:
        raise ValueError("schema, entities and policies must declare the same release_id")
    if policy_metadata.get("knowledge_version") != knowledge_version:
        raise ValueError("entities and policies must declare the same knowledge_version")

    existing_release_path = release_dir / "release.json"
    existing_release = (
        json.loads(existing_release_path.read_text(encoding="utf-8"))
        if existing_release_path.is_file()
        else {}
    )
    release = {
        "release_id": release_id,
        "ontology_version": ontology_version,
        "knowledge_version": knowledge_version,
        "status": "frozen",
        "frozen_at": str(existing_release.get("frozen_at") or "2026-07-28T00:00:00+08:00"),
        "experience_snapshot_hash": str(
            existing_release.get("experience_snapshot_hash") or "sha256:" + ("0" * 64)
        ),
        "semantic_hash": semantic_hash(schema, entities, policies),
        "files": {
            "entities.json": sha256_file(entities_path),
            "policies.json": sha256_file(policies_path),
            "schema.json": sha256_file(schema_path),
        },
    }
    existing_release_path.write_text(
        json.dumps(release, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return release


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal an existing versioned FusionAgent KG release.")
    parser.add_argument("--release-dir", default="kg/ontology/v1.0.0")
    args = parser.parse_args(argv)
    release = build_release(Path(args.release_dir))
    print(json.dumps(release, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
