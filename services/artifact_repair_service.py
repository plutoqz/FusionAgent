from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiLineString, MultiPoint, MultiPolygon
from shapely.ops import linemerge

from schemas.agent import RepairRecord
from schemas.quality_gate import QualityGateReport
from schemas.task_kind import TaskKind
from services.artifact_evaluation_service import evaluate_vector_artifact


_LINE_TYPES = {"LineString", "MultiLineString"}
_POLYGON_TYPES = {"Polygon", "MultiPolygon"}
_POINT_TYPES = {"Point", "MultiPoint"}
_PSEUDO_EMPTY_STRINGS = {"", "nan", "none", "<na>", "null"}


@dataclass
class ArtifactRepairResult:
    output_path: Path
    changed: bool
    applied_strategies: list[str] = field(default_factory=list)
    repair_records: list[RepairRecord] = field(default_factory=list)
    before_metrics: dict[str, Any] = field(default_factory=dict)
    after_metrics: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)


class ArtifactRepairService:
    def repair(
        self,
        *,
        artifact_path: Path,
        task_kind: TaskKind,
        quality_report: QualityGateReport,
        required_fields: list[str],
        output_dir: Path,
        repair_records: list[RepairRecord],
        source_artifact_paths: dict[str, Path | str] | None = None,
        max_attempts: int = 1,
    ) -> ArtifactRepairResult:
        del max_attempts
        artifact_path = Path(artifact_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        before_metrics = dict(quality_report.metrics or {})
        frame = gpd.read_file(artifact_path)
        original = frame.copy()
        applied: list[str] = []
        strategy_reports: list[dict[str, Any]] = []

        frame, changed, details = self._repair_schema_attributes(
            frame,
            task_kind=task_kind,
            required_fields=required_fields,
            source_artifact_paths=source_artifact_paths or {},
        )
        if changed:
            applied.append("schema_attribute_backfill")
            strategy_reports.append({"strategy": "schema_attribute_backfill", **details})

        if task_kind == TaskKind.road:
            frame, changed, details = self._preserve_road_names(frame)
            if changed:
                applied.append("road_name_preservation")
                strategy_reports.append({"strategy": "road_name_preservation", **details})

        if task_kind in {TaskKind.road, TaskKind.waterways}:
            frame, changed, details = self._repair_line_topology(frame)
            if changed:
                applied.append("line_topology_cleanup")
                strategy_reports.append({"strategy": "line_topology_cleanup", **details})

        frame, changed, details = self._repair_geometry_validity(frame, task_kind=task_kind)
        if changed:
            applied.append("geometry_validity_repair")
            strategy_reports.append({"strategy": "geometry_validity_repair", **details})

        if not applied:
            return ArtifactRepairResult(
                output_path=artifact_path,
                changed=False,
                before_metrics=before_metrics,
                after_metrics=before_metrics,
                report={
                    "input_path": str(artifact_path),
                    "output_path": str(artifact_path),
                    "changed": False,
                    "applied_strategies": [],
                    "strategy_reports": [],
                },
            )

        output_path = output_dir / f"{artifact_path.stem}.repair-{len(repair_records) + 1}.gpkg"
        frame = gpd.GeoDataFrame(frame, geometry=frame.geometry.name, crs=original.crs)
        frame.to_file(output_path, driver="GPKG")
        after_metrics = evaluate_vector_artifact(output_path, required_fields=required_fields)
        new_records = [
            RepairRecord(
                attempt_no=len(repair_records) + index + 1,
                strategy=strategy,
                step=0,
                message=f"Applied artifact repair strategy {strategy}.",
                success=True,
                timestamp=_utc_now(),
                reason_code=_reason_code_for_strategy(strategy),
                policy_source="quality_gate",
            )
            for index, strategy in enumerate(applied)
        ]
        report = {
            "input_path": str(artifact_path),
            "output_path": str(output_path),
            "changed": True,
            "applied_strategies": applied,
            "trigger_failure_reasons": list(quality_report.failure_reasons or []),
            "strategy_reports": strategy_reports,
            "before_metrics": before_metrics,
            "after_metrics": after_metrics,
        }
        return ArtifactRepairResult(
            output_path=output_path,
            changed=True,
            applied_strategies=applied,
            repair_records=new_records,
            before_metrics=before_metrics,
            after_metrics=after_metrics,
            report=report,
        )

    def _repair_schema_attributes(
        self,
        frame: gpd.GeoDataFrame,
        *,
        task_kind: TaskKind,
        required_fields: list[str],
        source_artifact_paths: dict[str, Path | str],
    ) -> tuple[gpd.GeoDataFrame, bool, dict[str, Any]]:
        result = frame.copy()
        changed = False
        filled: dict[str, int] = {}
        for field in required_fields:
            if field == result.geometry.name or field == "geometry":
                continue
            if task_kind == TaskKind.road and field in {"name", "osm_name", "road_name"}:
                continue
            if field not in result.columns:
                result[field] = pd.NA
                changed = True
            before = _missing_mask(result[field])
            if not before.any():
                continue
            values = self._backfill_values(result, field=field, task_kind=task_kind, source_artifact_paths=source_artifact_paths)
            if values is None:
                continue
            result.loc[before, field] = values.loc[before]
            after = _missing_mask(result[field])
            count = int(before.sum() - after.sum())
            if count > 0:
                filled[field] = count
                changed = True
        if changed:
            result = _mark_repair(result, "schema_attribute_backfill")
        return result, changed, {"filled_fields": filled}

    def _backfill_values(
        self,
        frame: gpd.GeoDataFrame,
        *,
        field: str,
        task_kind: TaskKind,
        source_artifact_paths: dict[str, Path | str],
    ) -> pd.Series | None:
        if field == "source_id":
            for candidate in ("source_id", "fusion_source", "source_layer", "source_name"):
                if candidate in frame.columns and candidate != field:
                    return _clean_series(frame[candidate])
            source_id = _single_source_id(source_artifact_paths)
            if source_id:
                return pd.Series([source_id] * len(frame), index=frame.index, dtype="object")
        if field == "source_feature_id":
            for candidate in ("source_feature_id", "osm_id", "supplement_segment_id", "FID_1", "FID", "id", "objectid", "fid"):
                if candidate in frame.columns and candidate != field:
                    return _clean_series(frame[candidate]).map(lambda value: str(value) if _not_empty(value) else pd.NA)
            source_values = self._backfill_values(
                frame,
                field="source_id",
                task_kind=task_kind,
                source_artifact_paths=source_artifact_paths,
            )
            if source_values is not None:
                return pd.Series(
                    [
                        f"{source_values.iloc[pos]}:{idx}" if _not_empty(source_values.iloc[pos]) else f"feature:{idx}"
                        for pos, idx in enumerate(frame.index)
                    ],
                    index=frame.index,
                    dtype="object",
                )
        if task_kind == TaskKind.road and field in {"name", "osm_name", "road_name"}:
            return _first_nonempty_series(frame, ("road_name", "name", "osm_name", "ref", "street_name"))
        if task_kind == TaskKind.road and field == "fusion_source":
            source_layer = _first_nonempty_series(frame, ("source_layer", "fusion_source"))
            if source_layer is not None:
                return source_layer.map(_road_fusion_source_from_layer)
            return pd.Series(["base_road_network"] * len(frame), index=frame.index, dtype="object")
        if task_kind == TaskKind.road and field == "match_role":
            source_layer = _first_nonempty_series(frame, ("source_layer", "match_role"))
            if source_layer is not None:
                return source_layer.map(_road_match_role_from_layer)
            return pd.Series(["base"] * len(frame), index=frame.index, dtype="object")
        if task_kind == TaskKind.road and field == "road_class":
            values = _first_nonempty_series(frame, ("road_class", "fclass", "highway", "class"))
            if values is not None:
                return values.fillna("road")
            return pd.Series(["road"] * len(frame), index=frame.index, dtype="object")
        if task_kind == TaskKind.road and field == "source_layer":
            values = _first_nonempty_series(frame, ("source_layer", "fusion_source"))
            if values is not None:
                return values.map(_road_source_layer)
            return pd.Series(["base"] * len(frame), index=frame.index, dtype="object")
        return None

    def _preserve_road_names(self, frame: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, bool, dict[str, Any]]:
        result = frame.copy()
        changed = False
        for column in ("name", "osm_name", "road_name"):
            if column not in result.columns:
                result[column] = ""
                changed = True
        candidates = _first_nonempty_series(result, ("road_name", "name", "osm_name", "ref", "street_name"))
        if candidates is None:
            return result, changed, {"filled_road_name": 0}
        missing_road_name = _missing_mask(result["road_name"])
        result.loc[missing_road_name, "road_name"] = candidates.loc[missing_road_name]
        missing_name = _missing_mask(result["name"])
        result.loc[missing_name, "name"] = candidates.loc[missing_name]
        if "source_layer" in result.columns:
            base_mask = ~result["source_layer"].astype(str).str.casefold().eq("supplement")
        else:
            base_mask = pd.Series(True, index=result.index)
        missing_osm_name = _missing_mask(result["osm_name"]) & base_mask
        result.loc[missing_osm_name, "osm_name"] = candidates.loc[missing_osm_name]
        filled = int(missing_road_name.sum() - _missing_mask(result["road_name"]).sum())
        if filled or changed:
            changed = True
            result = _mark_repair(result, "road_name_preservation")
        return result, changed, {"filled_road_name": filled}

    def _repair_geometry_validity(
        self,
        frame: gpd.GeoDataFrame,
        *,
        task_kind: TaskKind,
    ) -> tuple[gpd.GeoDataFrame, bool, dict[str, Any]]:
        result = frame.copy()
        changed = False
        repaired = 0
        dropped = 0
        fixed_geometries = []
        allowed = _allowed_geometry_types(task_kind)
        for geom in result.geometry:
            fixed = geom
            if fixed is not None and not fixed.is_empty and not fixed.is_valid:
                fixed = make_valid(fixed)
                repaired += 1
                changed = True
            fixed = _extract_allowed_geometry(fixed, allowed)
            if fixed is None or fixed.is_empty:
                dropped += 1
                fixed_geometries.append(None)
                changed = True
            else:
                fixed_geometries.append(fixed)
        result[result.geometry.name] = fixed_geometries
        before_len = len(result)
        result = result[result.geometry.notna() & ~result.geometry.is_empty].copy()
        if len(result) != before_len:
            changed = True
        if changed:
            result = _mark_repair(result, "geometry_validity_repair")
        return result, changed, {"repaired_geometries": repaired, "dropped_geometries": dropped}

    def _repair_line_topology(self, frame: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, bool, dict[str, Any]]:
        result = frame.copy()
        changed = False
        dropped_zero_length = 0
        normalized_multilines = 0
        new_geometries = []
        keep_mask = []
        for geom in result.geometry:
            line = _normalize_line_geometry(geom)
            if line is not geom:
                normalized_multilines += 1
                changed = True
            if line is None or line.is_empty or float(line.length) <= 0:
                dropped_zero_length += 1
                keep_mask.append(False)
                new_geometries.append(None)
                changed = True
                continue
            keep_mask.append(True)
            new_geometries.append(line)
        result[result.geometry.name] = new_geometries
        result = result[pd.Series(keep_mask, index=result.index)].copy()
        if changed:
            result = _mark_repair(result, "line_topology_cleanup")
        return result, changed, {
            "dropped_zero_length": dropped_zero_length,
            "normalized_multilines": normalized_multilines,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reason_code_for_strategy(strategy: str) -> str:
    return {
        "schema_attribute_backfill": "quality_missing_fields",
        "road_name_preservation": "quality_road_name_missing",
        "geometry_validity_repair": "quality_invalid_geometry",
        "line_topology_cleanup": "quality_line_topology_failed",
    }.get(strategy, "quality_artifact_repair")


def _missing_mask(series: pd.Series) -> pd.Series:
    values = series.astype("object")
    missing = values.map(pd.isna)
    text = values.fillna("").astype(str).str.strip().str.casefold()
    return missing | text.isin(_PSEUDO_EMPTY_STRINGS)


def _clean_series(series: pd.Series) -> pd.Series:
    result = series.astype("object")
    return result.mask(_missing_mask(result), pd.NA)


def _not_empty(value: object) -> bool:
    if pd.isna(value):
        return False
    return str(value).strip().casefold() not in _PSEUDO_EMPTY_STRINGS


def _first_nonempty_series(frame: gpd.GeoDataFrame, candidates: tuple[str, ...]) -> pd.Series | None:
    output = pd.Series([pd.NA] * len(frame), index=frame.index, dtype="object")
    found = False
    for column in candidates:
        if column not in frame.columns:
            continue
        values = _clean_series(frame[column])
        missing = _missing_mask(output)
        output.loc[missing] = values.loc[missing]
        found = True
    return output if found else None


def _single_source_id(source_artifact_paths: dict[str, Path | str]) -> str | None:
    source_ids = [str(source_id) for source_id, path in source_artifact_paths.items() if path]
    return source_ids[0] if len(source_ids) == 1 else None


def _road_source_layer(value: object) -> str:
    text = str(value or "").strip().casefold()
    if "supplement" in text or text in {"msft", "microsoft", "overture"}:
        return "supplement"
    return "base"


def _road_fusion_source_from_layer(value: object) -> str:
    return "supplement_road" if _road_source_layer(value) == "supplement" else "base_road_network"


def _road_match_role_from_layer(value: object) -> str:
    return "supplement_unmatched" if _road_source_layer(value) == "supplement" else "base"


def _mark_repair(frame: gpd.GeoDataFrame, strategy: str) -> gpd.GeoDataFrame:
    result = frame.copy()
    if "repair_strategy" not in result.columns:
        result["repair_strategy"] = ""
    existing = result["repair_strategy"].fillna("").astype(str)
    result["repair_strategy"] = existing.map(lambda value: f"{value};{strategy}".strip(";") if value else strategy)
    return result


def _allowed_geometry_types(task_kind: TaskKind) -> set[str]:
    if task_kind in {TaskKind.road, TaskKind.waterways}:
        return _LINE_TYPES
    if task_kind in {TaskKind.building, TaskKind.water_polygon}:
        return _POLYGON_TYPES
    if task_kind == TaskKind.poi:
        return _POINT_TYPES
    return set()


def _extract_allowed_geometry(geom, allowed: set[str]):
    if geom is None or geom.is_empty or not allowed:
        return geom
    geom_type = getattr(geom, "geom_type", "")
    if geom_type in allowed:
        return geom
    if geom_type != "GeometryCollection":
        return None
    parts = []
    for part in geom.geoms:
        extracted = _extract_allowed_geometry(part, allowed)
        if extracted is not None and not extracted.is_empty:
            if allowed == _LINE_TYPES and getattr(extracted, "geom_type", "") == "MultiLineString":
                parts.extend(list(extracted.geoms))
            elif allowed == _POLYGON_TYPES and getattr(extracted, "geom_type", "") == "MultiPolygon":
                parts.extend(list(extracted.geoms))
            else:
                parts.append(extracted)
    if not parts:
        return None
    if allowed == _LINE_TYPES:
        return MultiLineString(parts) if len(parts) > 1 else parts[0]
    if allowed == _POLYGON_TYPES:
        return MultiPolygon(parts) if len(parts) > 1 else parts[0]
    if allowed == _POINT_TYPES:
        return MultiPoint(parts) if len(parts) > 1 else parts[0]
    return parts[0]


def _normalize_line_geometry(geom):
    if geom is None or geom.is_empty:
        return None
    geom_type = getattr(geom, "geom_type", "")
    if geom_type == "LineString":
        return geom
    if geom_type == "MultiLineString":
        merged = linemerge(geom)
        return merged
    if geom_type == "GeometryCollection":
        lines = [part for part in geom.geoms if getattr(part, "geom_type", "") in _LINE_TYPES and not part.is_empty]
        if not lines:
            return None
        merged = linemerge(MultiLineString(lines))
        return merged
    return None
