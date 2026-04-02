from __future__ import annotations

import re


DEFAULT_TARGET_CRS = "EPSG:32643"


def normalize_target_crs(crs: str | None) -> str:
    if crs is None:
        return DEFAULT_TARGET_CRS

    value = crs.strip().upper()
    if not value:
        return DEFAULT_TARGET_CRS

    if not re.match(r"^EPSG:\d+$", value):
        raise ValueError(f"Invalid CRS format: {crs}. Expected like EPSG:32643.")
    return value

