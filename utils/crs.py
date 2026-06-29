from __future__ import annotations

import math
import re
from typing import Sequence

from pyproj import CRS
from pyproj.exceptions import CRSError


DEFAULT_TARGET_CRS = "EPSG:32643"
_EPSG_RE = re.compile(r"^EPSG:\d+$")
_BARE_EPSG_RE = re.compile(r"^\d+$")
_WGS84 = CRS.from_epsg(4326)


def normalize_explicit_target_crs(crs: str | None) -> str | None:
    if crs is None:
        return None

    value = crs.strip().upper()
    if not value:
        return None

    if _EPSG_RE.match(value):
        return value
    if _BARE_EPSG_RE.match(value):
        raise ValueError(f"Invalid CRS format: {crs}. Expected like EPSG:32643.")

    try:
        parsed = CRS.from_user_input(crs)
    except CRSError as exc:
        raise ValueError(f"Invalid CRS format: {crs}. Expected like EPSG:32643.") from exc

    epsg = parsed.to_epsg()
    if epsg is not None:
        return f"EPSG:{epsg}"
    if parsed.to_authority() == ("OGC", "CRS84") or parsed.equals(_WGS84, ignore_axis_order=True):
        return "EPSG:4326"

    raise ValueError(f"Invalid CRS format: {crs}. Expected like EPSG:32643.")


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
