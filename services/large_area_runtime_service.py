from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from shapely.ops import unary_union

from services.artifact_evaluation_service import evaluate_vector_artifact
from services.tile_partition_service import TileManifest, TileSpec


GeometryFamily = Literal["building", "polygon", "line", "point"]
DomainRunner = Callable[[TileSpec, dict[str, Path], Path, str, dict[str, Any]], tuple[Path, dict[str, Any]]]

_GEOMETRY_KEY = "_large_area_geometry_wkb"
_TILE_KEY = "_large_area_tile_id"
_SLICE_KEY = "_large_area_slice_name"
_INTERNAL_COLUMNS = (_GEOMETRY_KEY, _TILE_KEY, _SLICE_KEY)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            pass
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


@dataclass(frozen=True)
class LargeAreaSlice:
    name: str
    geometry_family: GeometryFamily
    sources: dict[str, Path]
    runner: DomainRunner
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LargeAreaTileOutput:
    tile_id: str
    slice_name: str
    output_path: Path
    feature_count: int
    working_bbox: tuple[float, float, float, float]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tile_id": self.tile_id,
            "slice_name": self.slice_name,
            "output_path": str(self.output_path),
            "feature_count": self.feature_count,
            "working_bbox": [float(value) for value in self.working_bbox],
            "stats": _json_safe(self.stats),
        }


@dataclass(frozen=True)
class LargeAreaRunResult:
    output_path: Path
    tile_count: int
    stitched_feature_count: int
    tile_outputs: list[LargeAreaTileOutput]
    evidence_paths: dict[str, Path]


class LargeAreaRuntimeService:
    def __init__(self, *, max_workers: int = 1) -> None:
        self.max_workers = max(1, int(max_workers))

    def run(
        self,
        *,
        run_id: str,
        job_type: str,
        tile_manifest: TileManifest,
        slices: list[LargeAreaSlice],
        output_dir: Path,
        target_crs: str,
        parameters: dict[str, Any],
        clip_boundary: gpd.GeoDataFrame | None = None,
    ) -> LargeAreaRunResult:
        if not slices:
            raise ValueError("LargeAreaRuntimeService requires at least one slice.")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        tile_manifest_path = output_dir / "tile_manifest.json"
        selected_sources_path = output_dir / "selected_sources.json"
        stitched_path = output_dir / "stitched_artifact.json"
        stats_path = output_dir / "fusion_stats.json"

        self._write_json(
            tile_manifest_path,
            {
                **tile_manifest.to_dict(),
                "manifest_mode": "shared_large_area_runtime",
                "tile_count": len(tile_manifest.tiles),
            },
        )
        self._write_json(
            selected_sources_path,
            {
                "run_id": run_id,
                "job_type": job_type,
                "slices": [
                    {
                        "name": slice_spec.name,
                        "geometry_family": slice_spec.geometry_family,
                        "sources": {source_id: str(path) for source_id, path in slice_spec.sources.items()},
                    }
                    for slice_spec in slices
                ],
            },
        )

        tile_outputs: list[LargeAreaTileOutput] = []
        for tile in tile_manifest.tiles:
            for slice_spec in slices:
                tile_dir = output_dir / "tiles" / tile.tile_id / slice_spec.name
                tile_dir.mkdir(parents=True, exist_ok=True)
                merged_parameters = {**parameters, **slice_spec.parameters}
                tile_sources = self._clip_sources_for_tile(
                    sources=slice_spec.sources,
                    tile=tile,
                    output_dir=tile_dir / "inputs",
                    target_crs=target_crs,
                )
                output_path, stats = slice_spec.runner(
                    tile,
                    tile_sources,
                    tile_dir,
                    target_crs,
                    merged_parameters,
                )
                feature_count = self._feature_count(output_path)
                tile_outputs.append(
                    LargeAreaTileOutput(
                        tile_id=tile.tile_id,
                        slice_name=slice_spec.name,
                        output_path=Path(output_path),
                        feature_count=feature_count,
                        working_bbox=tile.working_bbox,
                        stats=dict(stats or {}),
                    )
                )

        final_output = self._stitch(
            tile_outputs=tile_outputs,
            output_path=output_dir / f"{job_type}_large_area_fused.gpkg",
            target_crs=target_crs,
            clip_boundary=clip_boundary,
        )
        artifact_metrics = evaluate_vector_artifact(final_output, required_fields=["geometry"])
        stitched_feature_count = int(artifact_metrics.get("feature_count") or 0)
        evidence_payload = {
            "run_id": run_id,
            "job_type": job_type,
            "artifact_path": str(final_output),
            "tile_count": len(tile_manifest.tiles),
            "slice_count": len(slices),
            "stitched_feature_count": stitched_feature_count,
            "artifact_metrics": artifact_metrics,
            "tile_outputs": [item.to_dict() for item in tile_outputs],
            "slice_names": [item.name for item in slices],
        }
        self._write_json(stitched_path, evidence_payload)
        self._write_json(
            stats_path,
            {
                "run_id": run_id,
                "job_type": job_type,
                "tile_stats": [item.to_dict() for item in tile_outputs],
            },
        )
        return LargeAreaRunResult(
            output_path=final_output,
            tile_count=len(tile_manifest.tiles),
            stitched_feature_count=stitched_feature_count,
            tile_outputs=tile_outputs,
            evidence_paths={
                "tile_manifest": tile_manifest_path,
                "selected_sources": selected_sources_path,
                "stitched_artifact": stitched_path,
                "fusion_stats": stats_path,
            },
        )

    @staticmethod
    def _feature_count(path: Path) -> int:
        try:
            return int(len(gpd.read_file(path).index))
        except Exception:  # noqa: BLE001
            return 0

    def _stitch(
        self,
        *,
        tile_outputs: list[LargeAreaTileOutput],
        output_path: Path,
        target_crs: str,
        clip_boundary: gpd.GeoDataFrame | None,
    ) -> Path:
        frames: list[gpd.GeoDataFrame] = []
        for tile_output in tile_outputs:
            frame = gpd.read_file(tile_output.output_path)
            if frame.empty:
                continue
            frame = frame.set_crs(target_crs) if frame.crs is None else frame.to_crs(target_crs)
            frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
            if frame.empty:
                continue
            owner = box(*tile_output.working_bbox)
            owner_mask = frame.geometry.apply(owner.intersects)
            frame = frame[owner_mask].copy()
            if frame.empty:
                continue
            frame[_TILE_KEY] = tile_output.tile_id
            frame[_SLICE_KEY] = tile_output.slice_name
            frames.append(frame)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not frames:
            return self._write_frame(self._empty_frame(target_crs), output_path, target_crs=target_crs)

        combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
        combined = self._dedupe(combined)
        if clip_boundary is not None and not clip_boundary.empty:
            combined = self._clip_to_boundary(combined, clip_boundary=clip_boundary, target_crs=target_crs)
        if combined.empty:
            combined = self._empty_frame(target_crs, columns=combined.columns)
        return self._write_frame(combined, output_path, target_crs=target_crs)

    @staticmethod
    def _dedupe(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        result = frame.copy()
        for column in ("canonical_id", "source_feature_id", "osm_id", "id"):
            if column not in result.columns:
                continue
            populated = result[column].notna() & result[column].astype(str).str.len().gt(0)
            if populated.any():
                subset = [_SLICE_KEY, column] if _SLICE_KEY in result.columns else [column]
                keyed = result.loc[populated].drop_duplicates(subset=subset, keep="first")
                unkeyed = result.loc[~populated]
                result = gpd.GeoDataFrame(
                    pd.concat([keyed, unkeyed], ignore_index=True),
                    geometry="geometry",
                    crs=frame.crs,
                )
            break

        result[_GEOMETRY_KEY] = result.geometry.apply(lambda geom: geom.wkb_hex if geom is not None else None)
        subset = [_SLICE_KEY, _GEOMETRY_KEY] if _SLICE_KEY in result.columns else [_GEOMETRY_KEY]
        result = result.drop_duplicates(subset=subset, keep="first").copy()
        return result.drop(columns=list(_INTERNAL_COLUMNS), errors="ignore").reset_index(drop=True)

    @staticmethod
    def _clip_to_boundary(
        frame: gpd.GeoDataFrame,
        *,
        clip_boundary: gpd.GeoDataFrame,
        target_crs: str,
    ) -> gpd.GeoDataFrame:
        if frame.empty:
            return frame
        boundary_frame = clip_boundary.set_crs(target_crs) if clip_boundary.crs is None else clip_boundary.to_crs(target_crs)
        boundary_geometries = [
            geom for geom in boundary_frame.geometry.tolist() if geom is not None and not geom.is_empty
        ]
        if not boundary_geometries:
            return frame.iloc[0:0].copy()
        boundary = unary_union(boundary_geometries)
        clipped = frame.copy()
        clipped["geometry"] = clipped.geometry.apply(
            lambda geom: geom.intersection(boundary) if geom is not None and not geom.is_empty else geom
        )
        return clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty].copy()

    def _clip_sources_for_tile(
        self,
        *,
        sources: dict[str, Path],
        tile: TileSpec,
        output_dir: Path,
        target_crs: str,
    ) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        clipped: dict[str, Path] = {}
        tile_box = box(*tile.working_buffered_bbox)
        for source_id, source_path in sources.items():
            source_path = Path(source_path)
            try:
                frame = gpd.read_file(source_path)
            except Exception:  # noqa: BLE001
                clipped[source_id] = source_path
                continue
            if frame.crs is None:
                frame = frame.set_crs(target_crs)
            else:
                frame = frame.to_crs(target_crs)
            frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
            if not frame.empty:
                frame = frame[frame.geometry.intersects(tile_box)].copy()
            output_path = output_dir / f"{self._safe_source_name(source_id)}.gpkg"
            clipped[source_id] = self._write_frame(frame, output_path, target_crs=target_crs)
        return clipped

    @staticmethod
    def _write_frame(frame: gpd.GeoDataFrame, output_path: Path, *, target_crs: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output = frame.copy()
        if output.crs is None:
            output = output.set_crs(target_crs)
        else:
            output = output.to_crs(target_crs)
        if output.empty and len([column for column in output.columns if column != output.geometry.name]) == 0:
            output["_empty_schema"] = pd.Series(dtype="object")
        output.to_file(output_path, driver="GPKG")
        return output_path

    @staticmethod
    def _empty_frame(target_crs: str, columns: pd.Index | None = None) -> gpd.GeoDataFrame:
        data: dict[str, pd.Series] = {}
        for column in list(columns) if columns is not None else []:
            if column == "geometry" or column in _INTERNAL_COLUMNS:
                continue
            data[column] = pd.Series(dtype="object")
        if not data:
            data["source_id"] = pd.Series(dtype="object")
        return gpd.GeoDataFrame(
            data,
            geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs),
            crs=target_crs,
        )

    @staticmethod
    def _safe_source_name(source_id: str) -> str:
        safe = "".join(char if char.isalnum() else "_" for char in source_id)
        return safe.strip("_") or "source"

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")
