from __future__ import annotations

import json
import math
from typing import Any


def estimate_json_size_bytes(payload: object) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def normalize_llm_usage(raw: object) -> dict[str, int | None]:
    usage = raw if isinstance(raw, dict) else {}
    return {
        "prompt_tokens": _optional_non_negative_int(usage.get("prompt_tokens")),
        "completion_tokens": _optional_non_negative_int(usage.get("completion_tokens")),
        "total_tokens": _optional_non_negative_int(usage.get("total_tokens")),
    }


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and value >= 0:
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None
