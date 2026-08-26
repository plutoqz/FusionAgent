from __future__ import annotations

import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from benchmark_platform.canonical import (
    CANONICALIZATION_ID,
    CanonicalizationError,
    canonical_json_bytes,
    canonical_json_text,
    canonical_sha256,
    derive_seed,
    stable_id,
)
from benchmark_platform.models import (
    CanonicalIdentity,
    FailureClass,
    SeedDerivationInput,
)


def identity(payload: dict | None = None) -> CanonicalIdentity:
    return CanonicalIdentity(
        design_id="fusionagent.benchmark-design.v1",
        template_family_id="TF-CONTRACT-FIXTURE",
        capability_cell_id="BC-CAUSAL-01",
        partition="development",
        unit_index=0,
        seed=2026081901,
        payload=payload or {"task": "road", "priority": 1},
    )


def test_canonical_json_has_fixed_bytes_hash_and_newline_policy() -> None:
    value = {"z": [2, 1], "a": "洪水"}
    assert CANONICALIZATION_ID == "utf8-json-sorted-keys-compact-no-bom-no-newline.v1"
    assert canonical_json_bytes(value) == '{"a":"洪水","z":[2,1]}'.encode("utf-8")
    assert canonical_json_text(value) == '{"a":"洪水","z":[2,1]}'
    assert not canonical_json_bytes(value).startswith(b"\xef\xbb\xbf")
    assert not canonical_json_bytes(value).endswith(b"\n")
    assert canonical_sha256(value) == "sha256:4eaae318cac3d36cc771157884dd11fce75bb27ff485f787f56d03bd87804644"


def test_field_order_is_irrelevant_but_semantic_change_changes_hash_and_id() -> None:
    left = {"task": "road", "priority": 1}
    reordered = {"priority": 1, "task": "road"}
    changed = {"task": "road", "priority": 2}
    assert canonical_json_bytes(left) == canonical_json_bytes(reordered)
    assert canonical_sha256(left) == canonical_sha256(reordered)
    assert stable_id(identity(left)) == stable_id(identity(reordered))
    assert canonical_sha256(left) != canonical_sha256(changed)
    assert stable_id(identity(left)) != stable_id(identity(changed))


def test_every_identity_field_contributes_to_stable_id() -> None:
    baseline = identity()
    baseline_id = stable_id(baseline)
    mutations = {
        "design_id": "fusionagent.benchmark-design.v1-test",
        "template_family_id": "TF-CONTRACT-FIXTURE-ALT",
        "capability_cell_id": "BC-CAUSAL-02",
        "unit_index": 1,
        "seed": 2026081902,
        "payload": {"task": "road", "priority": 2},
    }
    for field, value in mutations.items():
        data = baseline.model_dump(mode="json")
        data[field] = value
        assert stable_id(CanonicalIdentity.model_validate(data)) != baseline_id, field


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_fail_closed(value: float) -> None:
    with pytest.raises(CanonicalizationError) as error:
        canonical_json_bytes({"value": value})
    assert error.value.failures[0].failure_class == FailureClass.CANONICAL_NON_FINITE_NUMBER
    assert error.value.failures[0].path == ("value",)


@pytest.mark.parametrize("value", [{1: "integer-key"}, {"value": {1, 2}}, b"bytes"])
def test_unsupported_json_types_fail_closed(value: object) -> None:
    with pytest.raises(CanonicalizationError) as error:
        canonical_json_bytes(value)
    assert error.value.failures[0].failure_class == FailureClass.CANONICAL_UNSUPPORTED_TYPE


def test_identity_requires_every_bound_field_and_development_partition() -> None:
    data = identity().model_dump(mode="json")
    data.pop("seed")
    with pytest.raises(ValidationError) as missing:
        CanonicalIdentity.model_validate(data)
    assert missing.value.errors()[0]["type"] == "missing"

    data["seed"] = 1
    data["partition"] = "independent_confirmation"
    with pytest.raises(ValidationError) as partition:
        CanonicalIdentity.model_validate(data)
    assert partition.value.errors()[0]["type"] == "literal_error"


def test_seed_derivation_is_deterministic_and_input_sensitive() -> None:
    seed_input = SeedDerivationInput(namespace="fusionagent.benchmark.development.v1", master_seed=7, unit_index=0)
    assert derive_seed(seed_input) == 18402870587084893168
    assert 0 <= derive_seed(seed_input) < 2**64
    assert derive_seed(seed_input) != derive_seed(
        SeedDerivationInput(namespace=seed_input.namespace, master_seed=7, unit_index=1)
    )
    assert derive_seed(seed_input) != derive_seed(
        SeedDerivationInput(namespace=seed_input.namespace, master_seed=8, unit_index=0)
    )
    assert derive_seed(seed_input) != derive_seed(
        SeedDerivationInput(namespace="other", master_seed=7, unit_index=0)
    )


def test_hash_identity_and_seed_are_stable_across_processes() -> None:
    expected = {
        "hash": canonical_sha256(identity().payload),
        "identity": stable_id(identity()),
        "seed": derive_seed(
            SeedDerivationInput(
                namespace="fusionagent.benchmark.development.v1",
                master_seed=7,
                unit_index=0,
            )
        ),
    }
    assert expected == {
        "hash": "sha256:e8a68b3ea7ab1099d918c62ec9308844d696f37abee8462846399e632ad2bd24",
        "identity": "bpi-sha256-fc58a3dd3e89926f64a798206d680b3355f1d0e7d8133638c2055cc3cf77d9da",
        "seed": 18402870587084893168,
    }
    script = """
import json
from benchmark_platform.canonical import canonical_sha256, derive_seed, stable_id
from benchmark_platform.models import CanonicalIdentity, SeedDerivationInput
identity = CanonicalIdentity.model_validate(json.loads(__import__('sys').argv[1]))
result = {
    'hash': canonical_sha256(identity.payload),
    'identity': stable_id(identity),
    'seed': derive_seed(SeedDerivationInput(namespace='fusionagent.benchmark.development.v1', master_seed=7, unit_index=0)),
}
print(json.dumps(result, sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, json.dumps(identity().model_dump(mode="json"))],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == expected
