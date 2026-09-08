from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmark_platform.materializer import MemberMaterializerError, materialize_members, merge_v2_extension
from benchmark_platform.generator import GeneratedMember, GeneratedUnit
from benchmark_platform.canonical import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/current/benchmark/v2/development_templates/base"


def _template(name: str) -> dict:
    return json.loads((PACKAGE / f"{name}.json").read_text(encoding="utf-8"))


def test_counterfactual_materializer_changes_only_declared_causal_path() -> None:
    template = _template("TF-CONTRACT-REQUIREDNESS")
    template["variables"]["invariants"] = [template["variables"]["invariants"][0]]
    members = materialize_members(template, 2, seed=7)
    assert members[0] != members[1]
    assert members[0]["task_state"]["tasks"][0]["source_states"][1]["availability"] == "available"
    assert members[1]["task_state"]["tasks"][0]["source_states"][1]["availability"] == "missing"


def test_invariant_materializer_varies_nuisance_without_causal_drift() -> None:
    template = _template("TF-WORDING-PARAPHRASE")
    members = materialize_members(template, 3, seed=0)
    assert [item["task_state"]["disaster_type"] for item in members] == ["generic", "emergency", "disaster"]
    assert all(item["task_state"]["tasks"][0]["task_kind"] == "poi" for item in members)


def test_materializer_is_deterministic_and_supports_order_variables() -> None:
    template = _template("TF-WORDING-PARAPHRASE")
    first = materialize_members(template, 3, seed=11)
    second = materialize_members(template, 3, seed=11)
    assert first == second
    assert len({json.dumps(item, sort_keys=True) for item in first}) == 3


def test_materializer_fails_closed_when_declared_path_is_not_in_payload() -> None:
    template = _template("TF-DELIVERY-STATE-TRACE")
    with pytest.raises(MemberMaterializerError, match="does not resolve"):
        materialize_members(template, 2)


def test_materialized_members_keep_hashes_and_relation_contract() -> None:
    template = _template("TF-CONTRACT-REQUIREDNESS")
    template["variables"]["invariants"] = [template["variables"]["invariants"][0]]
    payloads = materialize_members(template, 2)
    unit = GeneratedUnit(
        instance_id="BDV1-DEV-BC-CAUSAL-01-000",
        template_family_id=template["template_family_id"],
        capability_cell_id="BC-CAUSAL-01",
        partition="development",
        unit_index=0,
        unit_type="counterfactual_pair",
        seed=1,
        template_sha256=canonical_sha256(template),
        members=tuple(GeneratedMember(member_index=i, member_payload=p, member_sha256=canonical_sha256(p)) for i, p in enumerate(payloads)),
        instance_sha256="sha256:" + "0" * 64,
    )
    assert all(member.member_sha256 == canonical_sha256(member.member_payload) for member in unit.members)


def test_materializer_rejects_overlapping_authored_roles() -> None:
    template = _template("TF-CONTRACT-REQUIREDNESS")
    with pytest.raises(MemberMaterializerError, match="overlap"):
        materialize_members(template, 2)


def test_v2_extension_must_bind_exact_base_snapshot_before_materialization() -> None:
    base = _template("TF-ALGORITHM-CAPABILITY-GROUNDING")
    extension = json.loads((ROOT / "docs/current/benchmark/v2/development_templates/extensions/TF-ALGORITHM-CAPABILITY-GROUNDING.json").read_text(encoding="utf-8"))
    merged = merge_v2_extension(base, extension)
    members = materialize_members(merged, 2, seed=3)
    assert merged["v2_extensions"]["algorithm_grounding"]
    assert members[0] != members[1]
    tampered = copy.deepcopy(base)
    tampered["version"] = "9.9.9"
    with pytest.raises(MemberMaterializerError, match="hash"):
        merge_v2_extension(tampered, extension)


def test_materializer_does_not_mutate_template() -> None:
    template = _template("TF-WORDING-PARAPHRASE")
    original = copy.deepcopy(template)
    materialize_members(template, 3)
    assert template == original
