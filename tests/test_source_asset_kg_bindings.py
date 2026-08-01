from __future__ import annotations

import json
from pathlib import Path

from kg.knowledge_release import DEFAULT_POLICIES_PATH
from kg.policy_registry import KnowledgePolicyRegistry
from services.source_asset_service import SourceAssetResolution, SourceAssetService


def _mutated_registry(tmp_path: Path) -> KnowledgePolicyRegistry:
    payload = json.loads(DEFAULT_POLICIES_PATH.read_text(encoding="utf-8"))
    payload["source_runtime_bindings"]["source_id_aliases"]["raw.test.road"] = "raw.microsoft.road"
    for record in payload["source_runtime_bindings"]["vector_sources"]:
        if record["source_id"] == "raw.microsoft.road":
            record["remote_handler"] = "gns"
            break
    path = tmp_path / "policies.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return KnowledgePolicyRegistry(path)


def test_source_alias_and_remote_handler_are_driven_by_kg_policy(tmp_path: Path) -> None:
    service = SourceAssetService(
        repo_root=tmp_path,
        cache_dir=tmp_path / "cache",
        prefer_local_data=False,
        policy_registry=_mutated_registry(tmp_path),
    )
    expected = SourceAssetResolution(
        source_id="raw.gns.poi",
        path=tmp_path / "gns.gpkg",
        source_mode="test",
        cache_hit=False,
        version_token="test",
    )
    service._resolve_gns_poi = lambda **_kwargs: expected  # type: ignore[method-assign]

    resolved = service.resolve_raw_source_path("raw.test.road")

    assert resolved is expected
