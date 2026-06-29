from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.aoi_resolution_service import ResolvedAOI
from services.runtime_source_aliases import BUILDING_HEIGHT_RASTER_PRIORITY_ORDER
from services.source_acquisition_policy import build_source_attempt
from utils.vector_clip import BBox


HEIGHT_RASTER_ACQUISITION_SKILL_ID = "skill.source_acquisition.building_height_raster"
HEIGHT_RASTER_ACQUISITION_SKILL_NAME = "Building Height Raster Acquisition"
DEFAULT_HEIGHT_RASTER_MAX_SECONDS = 30

_SOURCE_ENV_SUFFIX = {
    "raw.google.open_buildings_2_5d.height_raster": "OPEN_BUILDINGS_2_5D",
    "raw.3d_globfp.building_height.raster": "3D_GLOBFP",
    "raw.google.building_height.raster": "GOOGLE",
    "raw.local.building_height.raster": "LOCAL",
}

_LOCAL_RASTER_PATTERNS = ("*.tif", "*.tiff", "*.vrt")

_LOCAL_RASTER_CANDIDATES = {
    "raw.google.open_buildings_2_5d.height_raster": (
        ("Data", "buildings", "height", "OpenBuildings2_5D"),
        ("Data", "buildings", "height", "open_buildings_2_5d"),
        ("Data", "buildings", "height", "google_open_buildings_2_5d"),
        ("data", "open_buildings_2_5d_2023_caracas_urban_height"),
        ("data", "open_buildings_2_5d_2023_caracas_bbox_height"),
        ("data", "open_buildings_2_5d_2023_ee_bbox_height"),
        ("data", "open_buildings_2_5d_2023"),
    ),
    "raw.3d_globfp.building_height.raster": (
        ("Data", "buildings", "height", "3D-GloBFP"),
        ("Data", "buildings", "height", "3d_globfp"),
        ("Data", "buildings", "height", "GloBFP"),
    ),
    "raw.google.building_height.raster": (
        ("Data", "buildings", "height", "Google"),
        ("Data", "buildings", "height", "google"),
        ("_processing", "google_open_buildings_temporal_2023"),
    ),
    "raw.local.building_height.raster": (
        ("Data", "buildings", "height"),
        ("Data", "buildings", "rasters"),
        ("height_rasters",),
    ),
}


@dataclass(frozen=True)
class MaterializedRasterHeightSource:
    source_id: str
    path: Path
    source_mode: str
    cache_hit: bool
    version_token: str
    elapsed_seconds: float


class RasterHeightSourceService:
    def __init__(
        self,
        *,
        repo_root: Path,
        cache_dir: Path,
        max_seconds: int | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_seconds = max(1, int(max_seconds or _height_raster_max_seconds()))

    def current_version_tokens(
        self,
        *,
        source_ids: list[str] | tuple[str, ...] = BUILDING_HEIGHT_RASTER_PRIORITY_ORDER,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> list[str]:
        tokens: list[str] = []
        for source_id in source_ids:
            local_path = self._resolve_configured_or_local_path(source_id, resolved_aoi=resolved_aoi)
            if local_path is not None:
                tokens.append(f"{source_id}:{_path_version_token(local_path)}")
                continue
            url = self._configured_url(source_id)
            if url:
                tokens.append(f"{source_id}:url:{_stable_token(url)}")
            else:
                tokens.append(f"missing:{source_id}")
        return tokens

    def materialize_preferred(
        self,
        *,
        target_dir: Path,
        request_bbox: BBox | None = None,
        resolved_aoi: ResolvedAOI | None = None,
        source_ids: list[str] | tuple[str, ...] = BUILDING_HEIGHT_RASTER_PRIORITY_ORDER,
        starting_attempt_no: int = 1,
    ) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
        del request_bbox
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        component_coverage: dict[str, dict[str, object]] = {}
        attempts: list[dict[str, object]] = []

        for source_id in source_ids:
            attempt_no = starting_attempt_no + len(attempts)
            try:
                materialized = self._materialize_one(
                    source_id,
                    target_dir=target_dir,
                    resolved_aoi=resolved_aoi,
                )
            except TimeoutError as exc:
                coverage, attempt = self._failed_evidence(
                    source_id,
                    attempt_no=attempt_no,
                    fault_class="SOURCE_DOWNLOAD_FAILED",
                    fault_message=str(exc),
                    source_mode="rapid_response_timeout",
                )
                component_coverage[source_id] = coverage
                attempts.append(attempt)
                continue
            except FileNotFoundError as exc:
                coverage, attempt = self._failed_evidence(
                    source_id,
                    attempt_no=attempt_no,
                    fault_class="SOURCE_MISSING",
                    fault_message=str(exc),
                    source_mode="missing_optional_height_raster",
                    status="no_coverage",
                )
                component_coverage[source_id] = coverage
                attempts.append(attempt)
                continue
            except PermissionError as exc:
                coverage, attempt = self._failed_evidence(
                    source_id,
                    attempt_no=attempt_no,
                    fault_class="UNAUTHORIZED",
                    fault_message=str(exc),
                    source_mode="unauthorized",
                )
                component_coverage[source_id] = coverage
                attempts.append(attempt)
                continue
            except Exception as exc:  # noqa: BLE001
                coverage, attempt = self._failed_evidence(
                    source_id,
                    attempt_no=attempt_no,
                    fault_class="PROVIDER_UNAVAILABLE",
                    fault_message=str(exc),
                    source_mode="provider_failed",
                )
                component_coverage[source_id] = coverage
                attempts.append(attempt)
                continue

            component_coverage[source_id] = self._available_coverage(materialized)
            attempts.append(
                _skill_attempt(
                    source_id=source_id,
                    status="available",
                    attempt_no=attempt_no,
                    coverage_status="available",
                    selected_for_fusion=True,
                    metadata={
                        "path": str(materialized.path),
                        "source_mode": materialized.source_mode,
                        "cache_hit": materialized.cache_hit,
                        "elapsed_seconds": round(materialized.elapsed_seconds, 3),
                    },
                )
            )
            break

        return component_coverage, attempts

    def _materialize_one(
        self,
        source_id: str,
        *,
        target_dir: Path,
        resolved_aoi: ResolvedAOI | None,
    ) -> MaterializedRasterHeightSource:
        started = time.monotonic()
        local_path = self._resolve_configured_or_local_path(source_id, resolved_aoi=resolved_aoi)
        if local_path is not None:
            return MaterializedRasterHeightSource(
                source_id=source_id,
                path=local_path,
                source_mode="local_raster",
                cache_hit=True,
                version_token=_path_version_token(local_path),
                elapsed_seconds=time.monotonic() - started,
            )

        url = self._configured_url(source_id)
        if not url:
            raise FileNotFoundError(f"No configured local path or URL for {source_id}")

        path, cache_hit = self._download_configured_url(source_id, url, started=started)
        if time.monotonic() - started > self.max_seconds and not cache_hit:
            raise TimeoutError(
                f"{source_id} download exceeded rapid-response budget of {self.max_seconds}s"
            )
        return MaterializedRasterHeightSource(
            source_id=source_id,
            path=path,
            source_mode="cache_reused_raster" if cache_hit else "downloaded_raster",
            cache_hit=cache_hit,
            version_token=_path_version_token(path),
            elapsed_seconds=time.monotonic() - started,
        )

    def _resolve_configured_or_local_path(
        self,
        source_id: str,
        *,
        resolved_aoi: ResolvedAOI | None,
    ) -> Path | None:
        configured = self._configured_path(source_id)
        if configured is not None:
            return _first_raster_path(configured, resolved_aoi=resolved_aoi)

        for root in _candidate_roots(self.repo_root):
            for rel_parts in _LOCAL_RASTER_CANDIDATES.get(source_id, ()):
                candidate = root.joinpath(*rel_parts)
                resolved = _first_raster_path(candidate, resolved_aoi=resolved_aoi)
                if resolved is not None:
                    return resolved
        return None

    def _configured_path(self, source_id: str) -> Path | None:
        mapping = _mapping_from_env("GEOFUSION_HEIGHT_RASTER_PATHS")
        value = mapping.get(source_id)
        suffix = _SOURCE_ENV_SUFFIX.get(source_id)
        if not value and suffix:
            value = os.getenv(f"GEOFUSION_HEIGHT_RASTER_{suffix}_PATH")
        if not value:
            return None
        return Path(str(value)).expanduser()

    def _configured_url(self, source_id: str) -> str | None:
        mapping = _mapping_from_env("GEOFUSION_HEIGHT_RASTER_URLS")
        value = mapping.get(source_id)
        suffix = _SOURCE_ENV_SUFFIX.get(source_id)
        if not value and suffix:
            value = os.getenv(f"GEOFUSION_HEIGHT_RASTER_{suffix}_URL")
        text = str(value or "").strip()
        return text or None

    def _download_configured_url(self, source_id: str, url: str, *, started: float) -> tuple[Path, bool]:
        parsed = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or f"{_stable_token(url)}.tif"
        if not Path(filename).suffix:
            filename = f"{filename}.tif"
        target = self.cache_dir / "height_rasters" / _source_slug(source_id) / _stable_token(url) / filename
        if target.exists() and target.stat().st_size > 0:
            return target, True
        target.parent.mkdir(parents=True, exist_ok=True)

        if parsed.scheme in {"", "file"}:
            source_path = Path(urllib.request.url2pathname(parsed.path) if parsed.scheme == "file" else url)
            if not source_path.exists():
                raise FileNotFoundError(f"Configured raster URL does not exist locally: {url}")
            shutil.copyfile(source_path, target)
            return target, False

        if parsed.scheme not in {"http", "https"}:
            raise FileNotFoundError(f"Unsupported raster URL scheme for {source_id}: {parsed.scheme}")

        with urllib.request.urlopen(url, timeout=self.max_seconds) as response:  # noqa: S310
            with target.open("wb") as handle:
                while True:
                    if time.monotonic() - started > self.max_seconds:
                        target.unlink(missing_ok=True)
                        raise TimeoutError(
                            f"{source_id} download exceeded rapid-response budget of {self.max_seconds}s"
                        )
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        return target, False

    @staticmethod
    def _available_coverage(materialized: MaterializedRasterHeightSource) -> dict[str, object]:
        return {
            "source_id": materialized.source_id,
            "source_mode": materialized.source_mode,
            "feature_count": None,
            "coverage_status": "available",
            "path": str(materialized.path),
            "source_form": "raster",
            "height_semantics": "estimated_height",
            "external_uncontrollable": False,
            "source_acquisition_skill": _skill_payload(),
            "rapid_response_policy": _rapid_response_policy(),
        }

    @staticmethod
    def _failed_evidence(
        source_id: str,
        *,
        attempt_no: int,
        fault_class: str,
        fault_message: str,
        source_mode: str,
        status: str = "attempted",
    ) -> tuple[dict[str, object], dict[str, object]]:
        external = fault_class in {
            "SOURCE_DOWNLOAD_FAILED",
            "NETWORK_FAILED",
            "PROVIDER_UNAVAILABLE",
            "NO_OFFICIAL_COVERAGE",
            "UNAUTHORIZED",
            "SOURCE_MISSING",
        }
        coverage = {
            "source_id": source_id,
            "source_mode": source_mode,
            "feature_count": 0,
            "coverage_status": "missing",
            "path": None,
            "error": fault_message,
            "fault_class": fault_class,
            "external_uncontrollable": external,
            "source_form": "raster",
            "height_semantics": "estimated_height",
            "source_acquisition_skill": _skill_payload(),
            "rapid_response_policy": _rapid_response_policy(),
        }
        attempt = _skill_attempt(
            source_id=source_id,
            status=status,
            attempt_no=attempt_no,
            fault_class=fault_class,
            fault_message=fault_message,
            coverage_status="missing",
            feature_count=0,
            selected_for_fusion=False,
            external_uncontrollable=external,
        )
        return coverage, attempt


def _first_raster_path(path: Path, *, resolved_aoi: ResolvedAOI | None) -> Path | None:
    path = Path(path)
    if path.is_file() and path.suffix.lower() in {".tif", ".tiff", ".vrt"}:
        return path
    if not path.exists() or not path.is_dir():
        return None

    matches = [
        candidate
        for pattern in _LOCAL_RASTER_PATTERNS
        for candidate in sorted(path.rglob(pattern))
        if candidate.is_file()
    ]
    if not matches:
        return None
    return _rank_raster_paths(matches, resolved_aoi=resolved_aoi)[0]


def _candidate_roots(repo_root: Path) -> list[Path]:
    root = Path(repo_root)
    candidates = [root]
    if root.name.casefold() in {"fusionagent_runtime_view", "runtime_view"}:
        candidates.append(root.parent)
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _rank_raster_paths(paths: list[Path], *, resolved_aoi: ResolvedAOI | None) -> list[Path]:
    hints = _aoi_tokens(resolved_aoi)

    def score(path: Path) -> tuple[int, int, str]:
        text = " ".join(_tokenize(part) for part in path.parts)
        token_score = sum(1 for token in hints if token and token in text)
        height_score = 1 if "height" in text or "hgt" in text else 0
        return (-(token_score * 10 + height_score), len(path.parts), str(path))

    return sorted(paths, key=score)


def _aoi_tokens(aoi: ResolvedAOI | None) -> set[str]:
    if aoi is None:
        return set()
    values = [aoi.query, aoi.display_name, aoi.country_name, aoi.country_code]
    tokens: set[str] = set()
    for value in values:
        tokens.update(part for part in _tokenize(value).split() if len(part) >= 2)
    return tokens


def _tokenize(value: object) -> str:
    text = str(value or "").casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def _mapping_from_env(name: str) -> dict[str, str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return {}
    text = raw.strip()
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return {str(key): str(value) for key, value in payload.items() if value is not None}
        return {}

    mapping: dict[str, str] = {}
    for item in text.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            mapping[key] = value
    return mapping


def _skill_attempt(
    *,
    source_id: str,
    status: str,
    attempt_no: int,
    coverage_status: str | None = None,
    feature_count: int | None = None,
    selected_for_fusion: bool = False,
    fault_class: str | None = None,
    fault_message: str | None = None,
    external_uncontrollable: bool | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return build_source_attempt(
        source_id=source_id,
        status=status,
        attempt_type="skill",
        attempt_no=attempt_no,
        channel="source_acquisition_skill",
        fault_class=fault_class,
        fault_message=fault_message,
        coverage_status=coverage_status,
        feature_count=feature_count,
        selected_for_fusion=selected_for_fusion,
        external_uncontrollable=external_uncontrollable,
        skill_id=HEIGHT_RASTER_ACQUISITION_SKILL_ID,
        skill_name=HEIGHT_RASTER_ACQUISITION_SKILL_NAME,
        capability="building_height_raster_materialization",
        metadata={
            "priority_order": list(BUILDING_HEIGHT_RASTER_PRIORITY_ORDER),
            "rapid_response_policy": _rapid_response_policy(),
            **dict(metadata or {}),
        },
    )


def _skill_payload() -> dict[str, object]:
    return {
        "skill_id": HEIGHT_RASTER_ACQUISITION_SKILL_ID,
        "skill_name": HEIGHT_RASTER_ACQUISITION_SKILL_NAME,
        "capability": "building_height_raster_materialization",
    }


def _rapid_response_policy() -> dict[str, object]:
    return {
        "max_seconds": _height_raster_max_seconds(),
        "fallback": "footprint_fusion_without_height",
        "required": False,
    }


def _height_raster_max_seconds() -> int:
    value = os.getenv("GEOFUSION_HEIGHT_RASTER_MAX_SECONDS")
    try:
        return max(1, int(str(value).strip())) if value else DEFAULT_HEIGHT_RASTER_MAX_SECONDS
    except ValueError:
        return DEFAULT_HEIGHT_RASTER_MAX_SECONDS


def _path_version_token(path: Path) -> str:
    path = Path(path)
    return hashlib.sha1(f"{path}:{int(path.stat().st_mtime)}:{path.stat().st_size}".encode("utf-8")).hexdigest()


def _stable_token(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]


def _source_slug(source_id: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in source_id).strip("_")
