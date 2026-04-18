from __future__ import annotations

import math
import re
from typing import Sequence


DEFAULT_TARGET_CRS = "EPSG:32643"


def normalize_explicit_target_crs(crs: str | None) -> str | None:
    if crs is None:
        return None

    value = crs.strip().upper()
    if not value:
        return None

    if not re.match(r"^EPSG:\d+$", value):
        raise ValueError(f"Invalid CRS format: {crs}. Expected like EPSG:32643.")
    return value


def derive_default_target_crs(bbox: Sequence[float] | None) -> str:
    if bbox is None or len(bbox) != 4:
        return DEFAULT_TARGET_CRS

    minx, miny, maxx, maxy = (float(item) for item in bbox)
    lon = (minx + maxx) / 2.0
    lat = (miny + maxy) / 2.0
    if not math.isfinite(lon) or not math.isfinite(lat):
        return DEFAULT_TARGET_CRS

    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(60, max(1, zone))
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return f"EPSG:{epsg}"


def resolve_target_crs(crs: str | None, *, bbox: Sequence[float] | None = None) -> str:
    explicit = normalize_explicit_target_crs(crs)
    if explicit is not None:
        return explicit
    return derive_default_target_crs(bbox)


def normalize_target_crs(crs: str | None) -> str:
    return resolve_target_crs(crs)
