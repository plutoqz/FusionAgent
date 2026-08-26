from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmark_platform.crosswalk import CrosswalkError, validate_crosswalk
from benchmark_platform.design_loader import (
    DESIGN_COMMIT,
    DESIGN_TAG,
    DesignLoaderError,
    load_frozen_design_bundle,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DESIGN_ROOT = REPO_ROOT / "docs/current/benchmark/v1"
FIXTURE = REPO_ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def known_template() -> dict:
    template = load_fixture()
    template["task_state"]["tasks"][0]["contract_ids"] = ["contract.road.fused.v1"]
    template["crosswalk"]["references"][0]["reference_id"] = "contract.road.fused.v1"
    return template


def test_frozen_design_bundle_and_known_crosswalk_load() -> None:
    bundle = load_frozen_design_bundle(str(DESIGN_ROOT), repo_root=str(REPO_ROOT))
    assert bundle.design_tag == DESIGN_TAG
    assert bundle.design_commit == DESIGN_COMMIT
    assert len(bundle.matrix["cells"]) == 17
    report = validate_crosswalk(bundle, known_template())
    assert report.reference_count == 1
    assert report.bindings[0].registry in {"entities.product_contracts", "policies.output_contracts"}


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda x: x["crosswalk"].update(kg_release_id="wrong"), "wrong_kg_release"),
        (lambda x: x["crosswalk"]["references"].__setitem__(0, {**x["crosswalk"]["references"][0], "reference_id": "unknown.contract"}), "unknown_id"),
        (lambda x: x["crosswalk"]["references"].append(copy.deepcopy(x["crosswalk"]["references"][0])), "duplicate_binding"),
    ],
)
def test_crosswalk_fail_closed(mutate, code: str) -> None:
    bundle = load_frozen_design_bundle(str(DESIGN_ROOT), repo_root=str(REPO_ROOT))
    template = known_template()
    mutate(template)
    with pytest.raises(CrosswalkError) as error:
        validate_crosswalk(bundle, template)
    assert error.value.failures[0].details["code"] == code


def test_crosswalk_rejects_ambiguous_registry_binding() -> None:
    bundle = load_frozen_design_bundle(str(DESIGN_ROOT), repo_root=str(REPO_ROOT))
    policies = copy.deepcopy(bundle.kg_policies)
    road = next(item for item in policies["output_contracts"] if item["contract_id"] == "contract.road.fused.v1")
    policies["output_contracts"].append(copy.deepcopy(road))
    altered = bundle.model_copy(update={"kg_policies": policies})
    with pytest.raises(CrosswalkError) as error:
        validate_crosswalk(altered, known_template())
    assert error.value.failures[0].details["code"] == "ambiguous_binding"


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"expected_tag": "wrong-tag"}, "identity_mismatch"),
        ({"expected_commit": "0" * 40}, "identity_mismatch"),
    ],
)
def test_loader_rejects_binding_arguments(kwargs, code: str) -> None:
    with pytest.raises(DesignLoaderError) as error:
        load_frozen_design_bundle(str(DESIGN_ROOT), repo_root=str(REPO_ROOT), **kwargs)
    assert error.value.failures[0].details["code"] == code


def test_loader_rejects_design_asset_tamper(tmp_path: Path) -> None:
    copied = tmp_path / "design"
    copied.mkdir()
    for path in DESIGN_ROOT.iterdir():
        if path.is_file():
            (copied / path.name).write_bytes(path.read_bytes())
    target = copied / "capability_matrix.json"
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(DesignLoaderError) as error:
        load_frozen_design_bundle(str(copied), repo_root=str(REPO_ROOT))
    assert error.value.failures[0].details["code"] == "asset_hash_mismatch"


def test_loader_rejects_protocol_manifest_hash_tamper(tmp_path: Path) -> None:
    copied = tmp_path / "design"
    copied.mkdir()
    for path in DESIGN_ROOT.iterdir():
        if path.is_file():
            (copied / path.name).write_bytes(path.read_bytes())
    manifest = copied / "freeze_manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["files"][0]["sha256"] = "sha256:" + "0" * 64
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DesignLoaderError) as error:
        load_frozen_design_bundle(str(copied), repo_root=str(REPO_ROOT))
    assert error.value.failures[0].details["code"] == "asset_hash_mismatch"


def test_p2_does_not_create_instance_or_output_roots() -> None:
    bundle = load_frozen_design_bundle(str(DESIGN_ROOT), repo_root=str(REPO_ROOT))
    validate_crosswalk(bundle, known_template())
    assert not Path(r"D:\code\fusionagent-evidence\benchmark-platform\development-v1").exists()
