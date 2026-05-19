from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from fusion_algorithms.road_fusion import run_road_segment_match_topology
from fusion_algorithms.water_fusion import fuse_water_polygons
from kg.source_catalog import build_data_sources
from kg.track_b_source_contract import TRACK_B_THEME_CONTRACTS
from services.artifact_evaluation_service import evaluate_vector_artifact
from services.artifact_registry import ArtifactRegistry
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import RawVectorSourceService
from services.source_asset_service import SourceCoverageStatus
from services.tile_partition_service import TilePartitionService, TileSpec
from services.track_b_source_normalization import normalize_track_b_source_frame
from utils.shp_zip import validate_zip_has_shapefile


DEFAULT_THEME_SOURCE_IDS = {
    "road": "catalog.flood.road",
    "water": "catalog.flood.water",
    "poi": "catalog.generic.poi",
}


@dataclass(frozen=True)
class TileFusionArtifact:
    tile_id: str
    output_path: Path
    feature_count: int
    working_bbox: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tile_id": self.tile_id,
            "output_path": str(self.output_path),
            "feature_count": self.feature_count,
            "working_bbox": [float(value) for value in self.working_bbox],
        }


class TrackBNationalScaleService:
    def __init__(self, *, root_dir: Path, cache_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.registry = ArtifactRegistry(index_path=self.cache_dir / "artifact_registry.json")
        self.raw_source_service = RawVectorSourceService(
            root_dir=self.root_dir,
            registry=self.registry,
            cache_dir=self.cache_dir / "raw_source_cache",
        )
        self.bundle_provider = LocalBundleCatalogProvider(
            self.root_dir,
            raw_source_service=self.raw_source_service,
        )
        self.source_index = {source.source_id: source for source in build_data_sources()}

    def build_theme_evidence(
        self,
        *,
        job_type: str,
        source_id: str | None,
        request_bbox: tuple[float, float, float, float],
        target_crs: str,
        output_root: Path,
        tile_width_m: float,
        tile_height_m: float,
        overlap_m: float = 0.0,
    ) -> dict[str, Any]:
        theme = str(job_type).strip().lower()
        if theme not in {"road", "water", "poi"}:
            raise ValueError(f"Unsupported Track B national-scale theme={job_type}")
        selected_source_id = source_id or DEFAULT_THEME_SOURCE_IDS[theme]
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        timings: dict[str, float] = {}

        bundle_started = time.perf_counter()
        materialized = self.bundle_provider.materialize_with_fallback(
            source_id=selected_source_id,
            request_bbox=request_bbox,
            target_dir=output_root / "input_bundle",
            target_crs=target_crs,
        )
        timings["bundle_materialize_sec"] = time.perf_counter() - bundle_started

        component_source_ids = list(materialized.component_coverage.keys())
        if not component_source_ids:
            raise ValueError(f"No component sources were materialized for {selected_source_id}")
        osm_source_id = component_source_ids[0]
        ref_source_id = component_source_ids[1] if len(component_source_ids) > 1 else None

        extract_dir = output_root / "_extract"
        osm_shp = validate_zip_has_shapefile(materialized.osm_zip_path, extract_dir / "osm")
        ref_shp = validate_zip_has_shapefile(materialized.ref_zip_path, extract_dir / "ref")

        normalization_started = time.perf_counter()
        normalized_dir = output_root / "normalized"
        normalized_dir.mkdir(parents=True, exist_ok=True)
        osm_normalized = normalize_track_b_source_frame(
            osm_source_id,
            gpd.read_file(osm_shp),
            target_crs=target_crs,
        )
        ref_normalized = (
            normalize_track_b_source_frame(ref_source_id, gpd.read_file(ref_shp), target_crs=target_crs)
            if ref_source_id is not None
            else _empty_frame(target_crs)
        )
        osm_normalized_path = self._write_gpkg(
            osm_normalized,
            normalized_dir / f"{osm_source_id.replace('.', '_')}.gpkg",
            target_crs=target_crs,
        )
        ref_normalized_path = (
            self._write_gpkg(
                ref_normalized,
                normalized_dir / f"{ref_source_id.replace('.', '_')}.gpkg",
                target_crs=target_crs,
            )
            if ref_source_id is not None
            else None
        )
        supplemental_summary = self._materialize_supplemental_normalized_sources(
            theme=theme,
            request_bbox=request_bbox,
            target_crs=target_crs,
            normalized_dir=normalized_dir / "supplemental",
            selected_component_ids=set(component_source_ids),
        )
        timings["normalize_sec"] = time.perf_counter() - normalization_started

        tile_manifest = TilePartitionService(
            tile_width_m=tile_width_m,
            tile_height_m=tile_height_m,
            overlap_m=overlap_m,
        ).partition_bbox(
            bbox=request_bbox,
            bbox_crs="EPSG:4326",
            working_crs=target_crs,
        )
        tile_payload = tile_manifest.to_dict()
        tile_payload["manifest_mode"] = "national_bbox_tiling"
        tile_payload["tile_count"] = len(tile_manifest.tiles)
        (output_root / "tile_manifest.json").write_text(
            json.dumps(tile_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        tile_started = time.perf_counter()
        tile_dir = output_root / "tiles"
        tile_dir.mkdir(parents=True, exist_ok=True)
        tile_results: list[TileFusionArtifact] = []
        for tile in tile_manifest.tiles:
            tile_output = self._run_tile_fusion(
                theme=theme,
                tile=tile,
                osm_frame=osm_normalized,
                ref_frame=ref_normalized,
                target_crs=target_crs,
                tile_dir=tile_dir / tile.tile_id,
            )
            tile_results.append(tile_output)
        timings["tile_fusion_sec"] = time.perf_counter() - tile_started

        stitch_started = time.perf_counter()
        final_output = self._stitch_tile_outputs(
            tile_results=tile_results,
            output_path=output_root / f"{theme}_national_scale_fused.gpkg",
            target_crs=target_crs,
        )
        timings["stitch_sec"] = time.perf_counter() - stitch_started

        selected_coverage = _jsonable_component_coverage(materialized.component_coverage)
        claim_state = self._claim_state(selected_coverage)
        artifact_metrics = evaluate_vector_artifact(final_output, required_fields=["geometry"])
        stitched_artifact_path = output_root / "stitched_artifact.json"
        stitched_artifact_payload = {
            "job_type": theme,
            "artifact_path": str(final_output),
            "tile_count": len(tile_results),
            "stitched_feature_count": int(artifact_metrics.get("feature_count") or 0),
            "artifact_metrics": artifact_metrics,
            "tile_outputs": [item.to_dict() for item in tile_results],
        }
        stitched_artifact_path.write_text(
            json.dumps(stitched_artifact_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        source_profile_snapshot = {
            "snapshot_mode": "track_b_national_scale",
            "job_type": theme,
            "requested_source_id": selected_source_id,
            "selected_source_id": materialized.source_id or selected_source_id,
            "fallback_from_source_id": materialized.fallback_from,
            "component_source_ids": component_source_ids,
            "selected_profiles": [
                self._profile_snapshot_entry(source_id=item, artifact_path=path)
                for item, path in [
                    (osm_source_id, osm_normalized_path),
                    (ref_source_id, ref_normalized_path),
                ]
                if item is not None and path is not None
            ],
            "supplemental_profiles": list(supplemental_summary.values()),
        }
        (output_root / "source_profile_snapshot.json").write_text(
            json.dumps(source_profile_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        selected_sources_payload = {
            "job_type": theme,
            "requested_source_id": selected_source_id,
            "selected_source_id": materialized.source_id or selected_source_id,
            "fallback_from_source_id": materialized.fallback_from,
            "source_mode": "national_bundle_materialized",
            "target_crs": target_crs,
            "component_source_ids": component_source_ids,
            "component_coverage": selected_coverage,
        }
        (output_root / "selected_sources.json").write_text(
            json.dumps(selected_sources_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        normalization_summary = {
            "selected_sources": {
                osm_source_id: self._normalization_entry(osm_source_id, osm_normalized, osm_normalized_path),
                **(
                    {ref_source_id: self._normalization_entry(ref_source_id, ref_normalized, ref_normalized_path)}
                    if ref_source_id is not None and ref_normalized_path is not None
                    else {}
                ),
            },
            "supplemental_sources": supplemental_summary,
        }
        (output_root / "normalization_summary.json").write_text(
            json.dumps(normalization_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        timing_payload = {
            "timings_sec": timings,
            "tile_count": len(tile_results),
            "stitched_feature_count": int(artifact_metrics.get("feature_count") or 0),
            "artifact_path": str(final_output),
        }
        (output_root / "timing.json").write_text(
            json.dumps(timing_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        inspection_summary = {
            "mode": "track_b_national_scale_evidence",
            "claim_state": claim_state,
            "run_type": "national_scale_utility",
            "job_type": theme,
            "requested_source_id": selected_source_id,
            "selected_source_id": materialized.source_id or selected_source_id,
            "fallback_from_source_id": materialized.fallback_from,
            "bbox": [float(value) for value in request_bbox],
            "target_crs": target_crs,
            "tile_count": len(tile_results),
            "artifact_path": str(final_output),
            "selected_component_source_ids": component_source_ids,
            "evidence": {
                "selected_sources": "selected_sources.json",
                "source_profile_snapshot": "source_profile_snapshot.json",
                "normalization_summary": "normalization_summary.json",
                "tile_manifest": "tile_manifest.json",
                "stitched_artifact": "stitched_artifact.json",
                "timing": "timing.json",
                "artifact_path": str(final_output),
            },
            "artifact_metrics": artifact_metrics,
            "operator_readable_summary": {
                "artifact_validity": bool(artifact_metrics.get("artifact_validity", False)),
                "feature_count": artifact_metrics.get("feature_count"),
                "component_coverage": selected_coverage,
                "supplemental_source_ids": sorted(supplemental_summary.keys()),
            },
        }
        (output_root / "inspection_summary.json").write_text(
            json.dumps(inspection_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "claim_state": claim_state,
            "output_root": str(output_root),
            "artifact_path": str(final_output),
            "tile_count": len(tile_results),
        }

    def _materialize_supplemental_normalized_sources(
        self,
        *,
        theme: str,
        request_bbox: tuple[float, float, float, float],
        target_crs: str,
        normalized_dir: Path,
        selected_component_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        normalized_dir.mkdir(parents=True, exist_ok=True)
        contract = TRACK_B_THEME_CONTRACTS[theme]
        candidate_ids = list(contract.manual_preload_source_ids) + list(contract.reservation_only_source_ids)
        summary: dict[str, dict[str, Any]] = {}
        for source_id in candidate_ids:
            if source_id in selected_component_ids:
                continue
            try:
                resolution = self.raw_source_service.source_asset_service.resolve_raw_source_path(
                    source_id,
                    request_bbox=request_bbox,
                )
                frame = gpd.read_file(resolution.path)
                normalized = normalize_track_b_source_frame(source_id, frame, target_crs=target_crs)
                artifact_path = self._write_gpkg(
                    normalized,
                    normalized_dir / f"{source_id.replace('.', '_')}.gpkg",
                    target_crs=target_crs,
                )
                summary[source_id] = self._normalization_entry(source_id, normalized, artifact_path)
                summary[source_id]["source_mode"] = resolution.source_mode
            except Exception as exc:  # noqa: BLE001
                summary[source_id] = {
                    "source_id": source_id,
                    "artifact_path": None,
                    "feature_count": 0,
                    "columns": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
        return summary

    def _run_tile_fusion(
        self,
        *,
        theme: str,
        tile: TileSpec,
        osm_frame: gpd.GeoDataFrame,
        ref_frame: gpd.GeoDataFrame,
        target_crs: str,
        tile_dir: Path,
    ) -> TileFusionArtifact:
        tile_dir.mkdir(parents=True, exist_ok=True)
        buffered = box(*tile.working_buffered_bbox)
        base_tile = osm_frame[osm_frame.geometry.intersects(buffered)].copy()
        ref_tile = ref_frame[ref_frame.geometry.intersects(buffered)].copy()

        if theme == "road":
            fused = run_road_segment_match_topology(base_tile, ref_tile)
        elif theme == "water":
            fused = fuse_water_polygons(base_tile, ref_tile)
        else:
            sources = {"OSM": base_tile}
            if not ref_tile.empty:
                sources["GNG"] = ref_tile
            fused = run_poi_geohash_priority_fusion(sources)

        if fused.crs is None:
            fused = fused.set_crs(target_crs)
        else:
            fused = fused.to_crs(target_crs)
        output_path = self._write_gpkg(fused, tile_dir / "fused.gpkg", target_crs=target_crs)
        return TileFusionArtifact(
            tile_id=tile.tile_id,
            output_path=output_path,
            feature_count=int(len(fused.index)),
            working_bbox=tile.working_bbox,
        )

    def _stitch_tile_outputs(
        self,
        *,
        tile_results: list[TileFusionArtifact],
        output_path: Path,
        target_crs: str,
    ) -> Path:
        frames: list[gpd.GeoDataFrame] = []
        for tile_result in tile_results:
            frame = gpd.read_file(tile_result.output_path)
            if frame.empty:
                continue
            if frame.crs is None:
                frame = frame.set_crs(target_crs)
            else:
                frame = frame.to_crs(target_crs)
            owner_box = box(*tile_result.working_bbox)
            owner_mask = frame.geometry.representative_point().apply(owner_box.covers)
            frame = frame[owner_mask].copy()
            if frame.empty:
                continue
            frame["_tile_id"] = tile_result.tile_id
            frames.append(frame)

        if not frames:
            return self._write_gpkg(_empty_frame(target_crs), output_path, target_crs=target_crs)

        combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
        combined["_geometry_wkb"] = combined.geometry.apply(lambda geom: geom.wkb_hex if geom is not None else None)
        combined = combined.drop_duplicates(subset=["_geometry_wkb"], keep="first").copy()
        combined = combined.drop(columns=["_geometry_wkb", "_tile_id"], errors="ignore")
        return self._write_gpkg(combined, output_path, target_crs=target_crs)

    def _profile_snapshot_entry(self, *, source_id: str, artifact_path: Path) -> dict[str, Any]:
        source = self.source_index.get(source_id)
        if source is None:
            return {"source_id": source_id, "artifact_path": str(artifact_path)}
        payload = asdict(source)
        payload["artifact_path"] = str(artifact_path)
        return payload

    @staticmethod
    def _normalization_entry(
        source_id: str,
        frame: gpd.GeoDataFrame,
        artifact_path: Path | None,
    ) -> dict[str, Any]:
        return {
            "source_id": source_id,
            "artifact_path": str(artifact_path) if artifact_path is not None else None,
            "feature_count": int(len(frame.index)),
            "columns": [str(column) for column in frame.columns],
        }

    @staticmethod
    def _claim_state(component_coverage: dict[str, dict[str, Any]]) -> str:
        feature_counts = [int(item.get("feature_count") or 0) for item in component_coverage.values()]
        if not feature_counts or max(feature_counts) == 0:
            return "national_scale_empty"
        if any(count == 0 for count in feature_counts[1:]):
            return "national_scale_partial_reference"
        return "national_scale_supported"

    @staticmethod
    def _write_gpkg(gdf: gpd.GeoDataFrame, output_path: Path, *, target_crs: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if gdf.crs is None:
            gdf = gdf.set_crs(target_crs)
        else:
            gdf = gdf.to_crs(target_crs)
        gdf.to_file(output_path, driver="GPKG")
        return output_path


def _empty_frame(target_crs: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs), crs=target_crs)


def _jsonable_component_coverage(component_coverage: dict[str, object]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for source_id, raw in (component_coverage or {}).items():
        if isinstance(raw, SourceCoverageStatus):
            payload[source_id] = {
                "source_id": raw.source_id,
                "source_mode": raw.source_mode,
                "feature_count": raw.feature_count,
                "coverage_status": raw.coverage_status,
                "path": str(raw.path) if raw.path is not None else None,
                "error": raw.error,
            }
        elif hasattr(raw, "__dataclass_fields__"):
            payload[source_id] = {
                "source_id": getattr(raw, "source_id", source_id),
                "source_mode": getattr(raw, "source_mode", None),
                "feature_count": getattr(raw, "feature_count", None),
                "coverage_status": getattr(raw, "coverage_status", None),
                "path": str(getattr(raw, "path", "")) if getattr(raw, "path", None) else None,
                "error": getattr(raw, "error", None),
            }
        elif isinstance(raw, dict):
            payload[source_id] = dict(raw)
        else:
            payload[source_id] = {"source_id": source_id, "value": raw}
    return payload
