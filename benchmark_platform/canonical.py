from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from pydantic import BaseModel

from benchmark_platform.models import (
    BenchmarkPlatformValidationError,
    CanonicalIdentity,
    FailureClass,
    FailureRecord,
    SeedDerivationInput,
)


CANONICALIZATION_ID = "utf8-json-sorted-keys-compact-no-bom-no-newline.v1"
IDENTITY_CONTRACT_ID = "fusionagent.benchmark-platform.identity.v1"
SEED_CONTRACT_ID = "fusionagent.benchmark-platform.seed.v1"


class CanonicalizationError(BenchmarkPlatformValidationError):
    pass


def _fail(failure_class: FailureClass, message: str, path: tuple[str | int, ...]) -> None:
    raise CanonicalizationError(
        [FailureRecord(failure_class=failure_class, message=message, path=path)]
    )


def _json_value(value: Any, path: tuple[str | int, ...] = ()) -> Any:
    if isinstance(value, BaseModel):
        return _json_value(value.model_dump(mode="json", exclude_none=False), path)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(FailureClass.CANONICAL_NON_FINITE_NUMBER, "non-finite numbers are forbidden", path)
        return value
    if isinstance(value, list):
        return [_json_value(item, (*path, index)) for index, item in enumerate(value)]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(
                    FailureClass.CANONICAL_UNSUPPORTED_TYPE,
                    f"object keys must be strings, received {type(key).__name__}",
                    path,
                )
            normalized[key] = _json_value(item, (*path, key))
        return normalized
    _fail(
        FailureClass.CANONICAL_UNSUPPORTED_TYPE,
        f"unsupported canonical JSON type: {type(value).__name__}",
        path,
    )


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _json_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_text(value: Any) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def canonical_sha256(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def stable_id(identity: CanonicalIdentity) -> str:
    identity_payload = {
        "identity_contract_id": IDENTITY_CONTRACT_ID,
        **identity.model_dump(mode="json", exclude_none=False),
    }
    digest = canonical_sha256(identity_payload).removeprefix("sha256:")
    return f"bpi-sha256-{digest}"


def derive_seed(seed_input: SeedDerivationInput) -> int:
    payload = {
        "seed_contract_id": SEED_CONTRACT_ID,
        **seed_input.model_dump(mode="json", exclude_none=False),
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)
