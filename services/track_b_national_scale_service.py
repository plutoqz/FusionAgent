from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import box

from fusion_algorithms.contracts import PoiFusionParams
from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from fusion_algorithms.road_conflation_v7 import RoadConflationV7Config, run_road_conflation_v7
from fusion_algorithms.water_fusion import fuse_water_polygons
from fusion_algorithms.waterways_conflation_v7 import (
    WaterwaysConflationV7Config,
    run_waterways_conflation_v7,
)
from kg.source_catalog import build_data_sources, get_catalog_bundle_spec
from kg.track_b_source_contract import TRACK_B_THEME_CONTRACTS
from services.aoi_resolution_service import ResolvedAOI
from services.artifact_evaluation_service import evaluate_vector_artifact
from services.artifact_registry import ArtifactRegistry
from services.autonomous_fusion_readiness_service import classify_autonomous_readiness
from services.local_bundle_catalog import LocalBundleCatalogProvider
from services.raw_vector_source_service import RawVectorSourceService
from services.source_asset_service import SourceCoverageStatus
from services.tile_partition_service import TilePartitionService, TileSpec
from services.tiled_building_runtime_service import TiledBuildingRuntimeService
from services.track_b_source_normalization import normalize_track_b_source_frame
from utils.shp_zip import validate_zip_has_shapefile


DEFAULT_THEME_SOURCE_IDS = {
    "building": "catalog.earthquake.building",
    "road": "catalog.flood.road",
    "water": "catalog.flood.water",
    "waterways": "catalog.flood.waterways",
    "poi": "catalog.generic.poi",
}

BUILDING_SOURCE_ALIASES = {
    "raw.osm.building": "OSM",
    "raw.microsoft.building": "MS",
    "raw.local.microsoft.building": "MICROSOFT_LOCAL",
    "raw.google.building": "GOOGLE",
    "raw.google.open_buildings.vector": "GOOGLE_OPEN_BUILDINGS",
    "raw.openbuildingmap.building": "OBM",
}

BUILDING_SOURCE_PRIORITY_ORDER = (
    "MS",
    "MICROSOFT_LOCAL",
    "OBM",
    "GOOGLE_OPEN_BUILDINGS",
    "GOOGLE",
    "OSM",
)

POI_SOURCE_ALIASES = {
    "raw.gns.poi": "GNG",
    "raw.geonames.poi": "GNG",
    "raw.google.poi": "GOOGLE",
    "raw.osm.poi": "OSM",
    "raw.rh.poi": "RH",
}

POI_SOURCE_PRIORITY_ORDER = ("GNG", "GOOGLE", "OSM", "RH")
CORE_SELECTED_POI_SOURCE_IDS = {"raw.gns.poi", "raw.google.poi", "raw.osm.poi"}


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
        resolved_aoi: ResolvedAOI | None = None,
    ) -> dict[str, Any]:
        theme = str(job_type).strip().lower()
        if theme not in {"building", "road", "water", "waterways", "poi"}:
            raise ValueError(f"Unsupported Track B national-scale theme={job_type}")
        selected_source_id = source_id or DEFAULT_THEME_SOURCE_IDS[theme]
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        timings: dict[str, float] = {}

        if theme == "building":
            return self._build_building_theme_evidence(
                selected_source_id=selected_source_id,
                request_bbox=request_bbox,
                target_crs=target_crs,
                output_root=output_root,
                tile_width_m=tile_width_m,
                tile_height_m=tile_height_m,
                overlap_m=overlap_m,
                resolved_aoi=resolved_aoi,
            )

        bundle_started = time.perf_counter()
        materialized = self.bundle_provider.materialize_with_fallback(
            source_id=selected_source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
            target_dir=output_root / "input_bundle",
            target_crs=target_crs,
        )
        timings["bundle_materialize_sec"] = time.perf_counter() - bundle_started

        coverage_component_source_ids = list(materialized.component_coverage.keys())
        if not coverage_component_source_ids:
            raise ValueError(f"No component sources were materialized for {selected_source_id}")
        bundle_component_source_ids = self._primary_component_source_ids(selected_source_id, coverage_component_source_ids)
        if theme == "poi":
            component_source_ids = self._poi_component_source_ids(coverage_component_source_ids)
        else:
            component_source_ids = bundle_component_source_ids
        extract_component_source_ids = bundle_component_source_ids if theme == "poi" else component_source_ids
        osm_source_id = extract_component_source_ids[0]
        ref_source_id = extract_component_source_ids[1] if len(extract_component_source_ids) > 1 else None

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
        selected_normalized_sources: dict[str, dict[str, Any]] = {
            osm_source_id: self._normalization_entry(osm_source_id, osm_normalized, osm_normalized_path),
            **(
                {ref_source_id: self._normalization_entry(ref_source_id, ref_normalized, ref_normalized_path)}
                if ref_source_id is not None and ref_normalized_path is not None
                else {}
            ),
        }
        poi_normalized_sources: dict[str, gpd.GeoDataFrame] = {}
        poi_normalized_paths: dict[str, Path] = {}
        if theme == "poi":
            poi_normalized_sources, poi_normalized_paths = self._materialize_poi_normalized_sources(
                component_source_ids=component_source_ids,
                component_coverage=materialized.component_coverage,
                target_crs=target_crs,
                normalized_dir=normalized_dir,
            )
            selected_normalized_sources = {
                source_id: self._normalization_entry(source_id, poi_normalized_sources[source_id], poi_normalized_paths[source_id])
                for source_id in component_source_ids
                if source_id in poi_normalized_sources and source_id in poi_normalized_paths
            }
        if theme in {"road", "waterways"}:
            supplemental_summary = {}
        elif theme == "water":
            supplemental_summary = self._materialize_water_line_supplemental_normalized_sources(
                component_coverage=materialized.component_coverage,
                target_crs=target_crs,
                normalized_dir=normalized_dir / "supplemental",
            )
        else:
            supplemental_summary = self._materialize_supplemental_normalized_sources(
                theme=theme,
                request_bbox=request_bbox,
                target_crs=target_crs,
                normalized_dir=normalized_dir / "supplemental",
                selected_component_ids=set(component_source_ids),
                resolved_aoi=resolved_aoi,
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

        fusion_summary: dict[str, Any] = {}
        if theme == "building":
            tile_started = time.perf_counter()
            final_output, tile_results, fusion_summary = self._run_building_national_fusion(
                tile_manifest=tile_manifest,
                target_crs=target_crs,
                output_root=output_root,
                selected_sources={
                    osm_source_id: osm_normalized_path,
                    **({ref_source_id: ref_normalized_path} if ref_source_id and ref_normalized_path else {}),
                },
                supplemental_summary=supplemental_summary,
            )
            timings["tile_fusion_sec"] = time.perf_counter() - tile_started
            timings["stitch_sec"] = 0.0
        elif theme in {"road", "waterways"}:
            tile_started = time.perf_counter()
            final_output, tile_results, fusion_summary = self._run_v7_national_line_fusion(
                theme=theme,
                request_bbox=request_bbox,
                target_crs=target_crs,
                output_root=output_root,
                tile_manifest=tile_manifest,
                base_source_id=osm_source_id,
                base_path=osm_normalized_path,
                supplement_source_id=ref_source_id,
                supplement_path=ref_normalized_path,
                base_frame=osm_normalized,
                supplement_frame=ref_normalized,
                resolved_aoi=resolved_aoi,
            )
            timings["tile_fusion_sec"] = time.perf_counter() - tile_started
            timings["stitch_sec"] = 0.0
        elif theme == "water":
            tile_started = time.perf_counter()
            final_output, tile_results, fusion_summary = self._run_water_national_large_area_fusion(
                tile_manifest=tile_manifest,
                target_crs=target_crs,
                output_root=output_root,
                base_source_id=osm_source_id,
                base_path=osm_normalized_path,
                supplement_source_id=ref_source_id,
                supplement_path=ref_normalized_path,
                supplemental_summary=supplemental_summary,
                resolved_aoi=resolved_aoi,
            )
            timings["tile_fusion_sec"] = time.perf_counter() - tile_started
            timings["stitch_sec"] = 0.0
        else:
            tile_started = time.perf_counter()
            tile_dir = output_root / "tiles"
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile_results = []
            for tile in tile_manifest.tiles:
                tile_output = self._run_tile_fusion(
                    theme=theme,
                    tile=tile,
                    osm_frame=osm_normalized,
                    ref_frame=ref_normalized,
                    supplemental_summary=supplemental_summary,
                    target_crs=target_crs,
                    tile_dir=tile_dir / tile.tile_id,
                    poi_sources=poi_normalized_sources,
                )
                tile_results.append(tile_output)
            timings["tile_fusion_sec"] = time.perf_counter() - tile_started

            stitch_started = time.perf_counter()
            final_output = self._stitch_tile_outputs(
                tile_results=tile_results,
                output_path=output_root / f"{theme}_national_scale_fused.gpkg",
                target_crs=target_crs,
                clip_boundary=self._country_boundary_for_aoi(resolved_aoi, target_crs=target_crs) if theme == "water" else None,
            )
            timings["stitch_sec"] = time.perf_counter() - stitch_started

        tile_count = self._evidence_tile_count(tile_results)
        selected_coverage = _jsonable_component_coverage(materialized.component_coverage)
        source_attempts = list(getattr(materialized, "provider_attempts", []) or [])
        autonomous_readiness = _write_autonomous_readiness(
            output_root=output_root,
            job_type=theme,
            component_coverage=selected_coverage,
            source_attempts=source_attempts,
        )
        claim_state = self._claim_state(selected_coverage)
        artifact_metrics = evaluate_vector_artifact(final_output, required_fields=["geometry"])
        stitched_artifact_path = output_root / "stitched_artifact.json"
        stitched_artifact_payload = {
            "job_type": theme,
            "artifact_path": str(final_output),
            "tile_count": tile_count,
            "stitched_feature_count": int(artifact_metrics.get("feature_count") or 0),
            "artifact_metrics": artifact_metrics,
            "tile_outputs": [item.to_dict() for item in tile_results],
            **({"fusion_summary": fusion_summary} if fusion_summary else {}),
            **(
                {
                    "algorithm_id": fusion_summary.get("algorithm_id"),
                    "config_snapshot": fusion_summary.get("config_snapshot"),
                }
                if fusion_summary.get("algorithm_id")
                else {}
            ),
        }
        stitched_artifact_path.write_text(
            json.dumps(stitched_artifact_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        selected_profile_paths = [
            (osm_source_id, osm_normalized_path),
            (ref_source_id, ref_normalized_path),
        ]
        if theme == "poi":
            selected_profile_paths = [
                (source_id, poi_normalized_paths[source_id])
                for source_id in component_source_ids
                if source_id in poi_normalized_paths
            ]

        source_profile_snapshot = {
            "snapshot_mode": "track_b_national_scale",
            "job_type": theme,
            "requested_source_id": selected_source_id,
            "selected_source_id": materialized.source_id or selected_source_id,
            "fallback_from_source_id": materialized.fallback_from,
            "component_source_ids": component_source_ids,
            "selected_profiles": [
                self._profile_snapshot_entry(source_id=item, artifact_path=path)
                for item, path in selected_profile_paths
                if item is not None and path is not None
            ],
            "supplemental_profiles": list(supplemental_summary.values()),
            **({"fusion_summary": fusion_summary} if fusion_summary else {}),
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
            **({"fusion_summary": fusion_summary} if fusion_summary else {}),
        }
        (output_root / "selected_sources.json").write_text(
            json.dumps(selected_sources_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        normalization_summary = {
            "selected_sources": selected_normalized_sources,
            "supplemental_sources": supplemental_summary,
        }
        (output_root / "normalization_summary.json").write_text(
            json.dumps(normalization_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        timing_payload = {
            "timings_sec": timings,
            "tile_count": tile_count,
            "stitched_feature_count": int(artifact_metrics.get("feature_count") or 0),
            "artifact_path": str(final_output),
            **({"fusion_summary": fusion_summary} if fusion_summary else {}),
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
            "tile_count": tile_count,
            "artifact_path": str(final_output),
            "selected_component_source_ids": component_source_ids,
            "evidence": {
                "selected_sources": "selected_sources.json",
                "source_profile_snapshot": "source_profile_snapshot.json",
                "normalization_summary": "normalization_summary.json",
                "autonomous_readiness": "autonomous_readiness.json",
                "tile_manifest": "tile_manifest.json",
                "stitched_artifact": "stitched_artifact.json",
                "timing": "timing.json",
                **({"fusion_stats": "fusion_stats.json"} if (output_root / "fusion_stats.json").exists() else {}),
                "artifact_path": str(final_output),
            },
            "autonomous_readiness": autonomous_readiness,
            "artifact_metrics": artifact_metrics,
            "operator_readable_summary": {
                "artifact_validity": bool(artifact_metrics.get("artifact_validity", False)),
                "feature_count": artifact_metrics.get("feature_count"),
                "component_coverage": selected_coverage,
                "supplemental_source_ids": sorted(supplemental_summary.keys()),
                **({"fusion_summary": fusion_summary} if fusion_summary else {}),
                **({"algorithm_id": fusion_summary.get("algorithm_id")} if fusion_summary.get("algorithm_id") else {}),
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
            "tile_count": tile_count,
        }

    def _build_building_theme_evidence(
        self,
        *,
        selected_source_id: str,
        request_bbox: tuple[float, float, float, float],
        target_crs: str,
        output_root: Path,
        tile_width_m: float,
        tile_height_m: float,
        overlap_m: float,
        resolved_aoi: ResolvedAOI | None,
    ) -> dict[str, Any]:
        timings: dict[str, float] = {}
        source_started = time.perf_counter()
        component_source_ids = self._primary_component_source_ids(
            selected_source_id,
            list(get_catalog_bundle_spec(selected_source_id).component_source_ids),
        )
        selected_source_summaries: dict[str, dict[str, Any]] = {}
        selected_sources: dict[str, Path] = {}
        component_coverage: dict[str, SourceCoverageStatus] = {}
        for source_id in component_source_ids:
            summary = self._building_raw_source_summary(source_id, resolved_aoi=resolved_aoi)
            selected_source_summaries[source_id] = summary
            artifact_path = self._summary_artifact_path(summary)
            if artifact_path is None:
                raise FileNotFoundError(f"Required building source is unavailable: {source_id}")
            selected_sources[source_id] = artifact_path
            component_coverage[source_id] = SourceCoverageStatus(
                source_id=source_id,
                source_mode=str(summary.get("source_mode") or "local_data_raw_runtime"),
                feature_count=int(summary.get("feature_count") or 0),
                coverage_status=str(summary.get("coverage_status") or "unknown"),
                path=artifact_path,
                error=summary.get("error"),
            )

        supplemental_summary = self._building_raw_supplemental_sources(
            selected_component_ids=set(component_source_ids),
            resolved_aoi=resolved_aoi,
        )
        road_summary = self._building_raw_source_summary("raw.osm.road", resolved_aoi=resolved_aoi)
        road_path = self._summary_artifact_path(road_summary)
        context_vectors = self._building_context_vectors(
            road_path=road_path,
            output_root=output_root,
            target_crs=target_crs,
        )
        timings["source_resolve_sec"] = time.perf_counter() - source_started
        timings["normalize_sec"] = 0.0
        timings["bundle_materialize_sec"] = 0.0

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
        final_output, tile_results, fusion_summary = self._run_building_national_fusion(
            tile_manifest=tile_manifest,
            target_crs=target_crs,
            output_root=output_root,
            selected_sources=selected_sources,
            supplemental_summary=supplemental_summary,
            vector_source_crs=self._building_vector_source_crs(
                list(selected_source_summaries.values()) + list(supplemental_summary.values())
            ),
            context_vectors=context_vectors,
            parameters={
                "large_tile_fallback_feature_threshold": 250_000,
            },
        )
        timings["tile_fusion_sec"] = time.perf_counter() - tile_started
        timings["stitch_sec"] = 0.0

        tile_count = self._evidence_tile_count(tile_results)
        selected_coverage = _jsonable_component_coverage(component_coverage)
        readiness_coverage = _building_readiness_coverage(
            selected_coverage=selected_coverage,
            supplemental_summary=supplemental_summary,
            road_summary=road_summary,
        )
        autonomous_readiness = _write_autonomous_readiness(
            output_root=output_root,
            job_type="building",
            component_coverage=readiness_coverage,
            source_attempts=[],
        )
        claim_state = self._claim_state(selected_coverage)
        artifact_metrics = evaluate_vector_artifact(final_output, required_fields=["geometry"])
        stitched_artifact_payload = {
            "job_type": "building",
            "artifact_path": str(final_output),
            "tile_count": tile_count,
            "stitched_feature_count": int(artifact_metrics.get("feature_count") or 0),
            "artifact_metrics": artifact_metrics,
            "tile_outputs": [item.to_dict() for item in tile_results],
            "fusion_summary": fusion_summary,
        }
        (output_root / "stitched_artifact.json").write_text(
            json.dumps(stitched_artifact_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        source_profile_snapshot = {
            "snapshot_mode": "track_b_national_scale",
            "job_type": "building",
            "runtime_mode": "raw_source_tiled_runtime",
            "requested_source_id": selected_source_id,
            "selected_source_id": selected_source_id,
            "fallback_from_source_id": None,
            "component_source_ids": component_source_ids,
            "selected_profiles": [
                self._profile_snapshot_entry(source_id=source_id, artifact_path=path)
                for source_id, path in selected_sources.items()
            ],
            "supplemental_profiles": list(supplemental_summary.values()),
            "fusion_summary": fusion_summary,
        }
        (output_root / "source_profile_snapshot.json").write_text(
            json.dumps(source_profile_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        selected_sources_payload = {
            "job_type": "building",
            "requested_source_id": selected_source_id,
            "selected_source_id": selected_source_id,
            "fallback_from_source_id": None,
            "source_mode": "raw_source_tiled_runtime",
            "target_crs": target_crs,
            "component_source_ids": component_source_ids,
            "component_coverage": selected_coverage,
            "fusion_summary": fusion_summary,
        }
        (output_root / "selected_sources.json").write_text(
            json.dumps(selected_sources_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        normalization_summary = {
            "runtime_mode": "raw_source_tiled_runtime",
            "selected_sources": selected_source_summaries,
            "supplemental_sources": supplemental_summary,
        }
        (output_root / "normalization_summary.json").write_text(
            json.dumps(normalization_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        timing_payload = {
            "timings_sec": timings,
            "tile_count": tile_count,
            "stitched_feature_count": int(artifact_metrics.get("feature_count") or 0),
            "artifact_path": str(final_output),
            "fusion_summary": fusion_summary,
        }
        (output_root / "timing.json").write_text(
            json.dumps(timing_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        inspection_summary = {
            "mode": "track_b_national_scale_evidence",
            "claim_state": claim_state,
            "run_type": "national_scale_utility",
            "job_type": "building",
            "runtime_mode": "raw_source_tiled_runtime",
            "requested_source_id": selected_source_id,
            "selected_source_id": selected_source_id,
            "fallback_from_source_id": None,
            "bbox": [float(value) for value in request_bbox],
            "target_crs": target_crs,
            "tile_count": tile_count,
            "artifact_path": str(final_output),
            "selected_component_source_ids": component_source_ids,
            "evidence": {
                "selected_sources": "selected_sources.json",
                "source_profile_snapshot": "source_profile_snapshot.json",
                "normalization_summary": "normalization_summary.json",
                "autonomous_readiness": "autonomous_readiness.json",
                "tile_manifest": "tile_manifest.json",
                "stitched_artifact": "stitched_artifact.json",
                "timing": "timing.json",
                "artifact_path": str(final_output),
            },
            "autonomous_readiness": autonomous_readiness,
            "artifact_metrics": artifact_metrics,
            "operator_readable_summary": {
                "artifact_validity": bool(artifact_metrics.get("artifact_validity", False)),
                "feature_count": artifact_metrics.get("feature_count"),
                "component_coverage": selected_coverage,
                "supplemental_source_ids": sorted(supplemental_summary.keys()),
                "fusion_summary": fusion_summary,
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
            "tile_count": tile_count,
        }

    def _building_raw_supplemental_sources(
        self,
        *,
        selected_component_ids: set[str],
        resolved_aoi: ResolvedAOI | None,
    ) -> dict[str, dict[str, Any]]:
        candidate_ids = [
            source_id
            for source_id in (
                list(TRACK_B_THEME_CONTRACTS["building"].official_remote_source_ids)
                + list(TRACK_B_THEME_CONTRACTS["building"].manual_preload_source_ids)
                + list(TRACK_B_THEME_CONTRACTS["building"].reservation_only_source_ids)
            )
            if source_id not in selected_component_ids
        ]
        summary: dict[str, dict[str, Any]] = {}
        for source_id in candidate_ids:
            summary[source_id] = self._building_raw_source_summary(source_id, resolved_aoi=resolved_aoi)
        return summary

    def _building_raw_source_summary(
        self,
        source_id: str,
        *,
        resolved_aoi: ResolvedAOI | None,
    ) -> dict[str, Any]:
        try:
            path = self.raw_source_service.resolve_local_source_path(source_id, resolved_aoi=resolved_aoi)
            info = pyogrio.read_info(path)
            raw_count = info.get("features")
            feature_count = int(raw_count) if raw_count is not None and int(raw_count) >= 0 else None
            raw_fields = info.get("fields")
            fields = [str(item) for item in list(raw_fields)] if raw_fields is not None else []
            crs = str(info.get("crs") or "").strip() or None
            return {
                "source_id": source_id,
                "artifact_path": str(path),
                "feature_count": feature_count,
                "coverage_status": self._coverage_status_for_feature_count(feature_count),
                "source_mode": "local_data_raw_runtime",
                "columns": fields,
                "crs": crs,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "source_id": source_id,
                "artifact_path": None,
                "feature_count": 0,
                "coverage_status": "empty",
                "source_mode": "missing_local_raw_runtime",
                "columns": [],
                "crs": None,
                "error": f"{type(exc).__name__}: {exc}",
            }

    @staticmethod
    def _coverage_status_for_feature_count(feature_count: int | None) -> str:
        if feature_count is None:
            return "unknown"
        if feature_count == 0:
            return "empty"
        return "available"

    @staticmethod
    def _summary_artifact_path(summary: dict[str, Any]) -> Path | None:
        raw = summary.get("artifact_path")
        if not raw:
            return None
        path = Path(str(raw))
        return path if path.exists() else None

    @staticmethod
    def _building_vector_source_crs(summaries: list[dict[str, Any]]) -> str:
        crs_values = {
            str(summary.get("crs") or "").strip()
            for summary in summaries
            if summary.get("artifact_path") and str(summary.get("crs") or "").strip()
        }
        if len(crs_values) == 1:
            return next(iter(crs_values))
        return "EPSG:4326"

    def _building_context_vectors(
        self,
        *,
        road_path: Path | None,
        output_root: Path,
        target_crs: str,
    ) -> dict[str, Path] | None:
        if road_path is None:
            return None
        road_frame = gpd.read_file(road_path)
        context_path = self._write_gpkg(
            road_frame,
            output_root / "context_vectors" / "raw_osm_road.gpkg",
            target_crs=target_crs,
        )
        return {"roads": context_path}

    def _materialize_supplemental_normalized_sources(
        self,
        *,
        theme: str,
        request_bbox: tuple[float, float, float, float],
        target_crs: str,
        normalized_dir: Path,
        selected_component_ids: set[str],
        resolved_aoi: ResolvedAOI | None,
    ) -> dict[str, dict[str, Any]]:
        normalized_dir.mkdir(parents=True, exist_ok=True)
        contract = TRACK_B_THEME_CONTRACTS[theme]
        candidate_ids = [
            source_id
            for source_id in (
                list(contract.official_remote_source_ids)
                + list(contract.manual_preload_source_ids)
                + list(contract.reservation_only_source_ids)
            )
            if source_id not in selected_component_ids
        ]
        summary: dict[str, dict[str, Any]] = {}
        for source_id in candidate_ids:
            try:
                resolution = self.raw_source_service.source_asset_service.resolve_raw_source_path(
                    source_id,
                    request_bbox=request_bbox,
                    aoi=resolved_aoi,
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

    @staticmethod
    def _primary_component_source_ids(
        selected_source_id: str,
        component_source_ids: list[str],
    ) -> list[str]:
        try:
            primary_ids = list(get_catalog_bundle_spec(selected_source_id).component_source_ids)
        except Exception:  # noqa: BLE001
            return component_source_ids
        return [source_id for source_id in primary_ids if source_id in component_source_ids] or component_source_ids

    @staticmethod
    def _poi_component_source_ids(component_source_ids: list[str]) -> list[str]:
        available = {"raw.gns.poi" if item == "raw.geonames.poi" else item for item in component_source_ids}
        ordered = [source_id for source_id in ("raw.gns.poi", "raw.google.poi", "raw.osm.poi", "raw.rh.poi") if source_id in available]
        ordered.extend(sorted(source_id for source_id in available if source_id not in ordered))
        return ordered

    def _materialize_poi_normalized_sources(
        self,
        *,
        component_source_ids: list[str],
        component_coverage: dict[str, object],
        target_crs: str,
        normalized_dir: Path,
    ) -> tuple[dict[str, gpd.GeoDataFrame], dict[str, Path]]:
        frames: dict[str, gpd.GeoDataFrame] = {}
        paths: dict[str, Path] = {}
        for source_id in component_source_ids:
            coverage = component_coverage.get(source_id)
            if coverage is None and source_id == "raw.gns.poi":
                coverage = component_coverage.get("raw.geonames.poi")
            path = self._coverage_path(coverage)
            is_core_selected = source_id in CORE_SELECTED_POI_SOURCE_IDS
            coverage_available = self._coverage_is_available(coverage)
            if path is None:
                if is_core_selected and coverage_available:
                    self._raise_selected_poi_materialization_error(source_id, None, "available coverage has no path")
                continue
            if not path.exists():
                if is_core_selected and coverage_available:
                    self._raise_selected_poi_materialization_error(
                        source_id,
                        path,
                        "available coverage path does not exist",
                    )
                continue
            try:
                source_path = path
                if path.suffix.lower() == ".zip":
                    source_path = validate_zip_has_shapefile(path, normalized_dir / f"extract_{source_id.replace('.', '_')}")
                normalized = normalize_track_b_source_frame(
                    source_id,
                    gpd.read_file(source_path),
                    target_crs=target_crs,
                )
                artifact_path = self._write_gpkg(
                    normalized,
                    normalized_dir / f"{source_id.replace('.', '_')}.gpkg",
                    target_crs=target_crs,
                )
                frames[source_id] = normalized
                paths[source_id] = artifact_path
            except Exception as exc:  # noqa: BLE001
                if is_core_selected and coverage_available:
                    self._raise_selected_poi_materialization_error(source_id, path, exc)
                continue
        return frames, paths

    def _materialize_water_line_supplemental_normalized_sources(
        self,
        *,
        component_coverage: dict[str, object],
        target_crs: str,
        normalized_dir: Path,
    ) -> dict[str, dict[str, Any]]:
        normalized_dir.mkdir(parents=True, exist_ok=True)
        summary: dict[str, dict[str, Any]] = {}
        for source_id in ("raw.osm.waterways", "raw.hydrorivers.water", "raw.local.pakistan.waterways"):
            coverage = component_coverage.get(source_id)
            path = self._coverage_path(coverage)
            if path is None or not path.exists():
                continue
            try:
                shp_path = validate_zip_has_shapefile(path, normalized_dir / f"extract_{source_id.replace('.', '_')}")
                frame = gpd.read_file(shp_path)
                normalized = normalize_track_b_source_frame(source_id, frame, target_crs=target_crs)
                artifact_path = self._write_gpkg(
                    normalized,
                    normalized_dir / f"{source_id.replace('.', '_')}.gpkg",
                    target_crs=target_crs,
                )
                summary[source_id] = self._normalization_entry(source_id, normalized, artifact_path)
                summary[source_id]["source_mode"] = self._coverage_source_mode(coverage)
            except Exception as exc:  # noqa: BLE001
                summary[source_id] = {
                    "source_id": source_id,
                    "artifact_path": None,
                    "feature_count": 0,
                    "columns": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
        return summary

    def _run_building_national_fusion(
        self,
        *,
        tile_manifest,
        target_crs: str,
        output_root: Path,
        selected_sources: dict[str, Path | None],
        supplemental_summary: dict[str, dict[str, Any]],
        vector_source_crs: str | None = None,
        context_vectors: dict[str, Path] | None = None,
        parameters: dict[str, object] | None = None,
    ) -> tuple[Path, list[TileFusionArtifact], dict[str, Any]]:
        vector_sources, source_id_by_alias = self._building_vector_sources(
            selected_sources=selected_sources,
            supplemental_summary=supplemental_summary,
        )
        if not vector_sources:
            output_path = output_root / "runtime_output" / "fused_buildings.gpkg"
            self._write_gpkg(_empty_frame(target_crs), output_path, target_crs=target_crs)
            return output_path, [], {"vector_source_ids": [], "source_priority_order": []}

        source_priority_order = tuple(
            alias for alias in BUILDING_SOURCE_PRIORITY_ORDER if alias in vector_sources
        ) + tuple(alias for alias in vector_sources if alias not in BUILDING_SOURCE_PRIORITY_ORDER)
        runtime = TiledBuildingRuntimeService(max_workers=1)
        event_path = output_root / "building_tile_events.jsonl"
        if event_path.exists():
            event_path.unlink()

        def on_event(event_type: str, payload: dict[str, Any]) -> None:
            event_payload = {"event": event_type, **payload}
            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event_payload, ensure_ascii=False) + "\n")

        result = runtime.run_tiled_multisource_building_job(
            run_id="track-b-national-building",
            tile_manifest=tile_manifest,
            vector_sources=vector_sources,
            output_dir=output_root / "runtime_output",
            target_crs=target_crs,
            vector_source_crs=vector_source_crs or target_crs,
            context_vectors=context_vectors,
            source_priority_order=source_priority_order,
            parameters=parameters,
            on_event=on_event,
        )
        tile_results = [
            TileFusionArtifact(
                tile_id=item.tile_id,
                output_path=item.output_path,
                feature_count=item.feature_count,
                working_bbox=item.working_bbox,
            )
            for item in result.tile_outputs
        ]
        fusion_summary = {
            "vector_source_ids": [source_id_by_alias[alias] for alias in source_priority_order],
            "vector_source_aliases": {source_id_by_alias[alias]: alias for alias in source_priority_order},
            "source_priority_order": list(source_priority_order),
            "runtime_parameters": dict(parameters or {}),
            "runtime_event_log": str(event_path),
        }
        return result.output_path, tile_results, fusion_summary

    def _run_water_national_large_area_fusion(
        self,
        *,
        tile_manifest,
        target_crs: str,
        output_root: Path,
        base_source_id: str,
        base_path: Path,
        supplement_source_id: str | None,
        supplement_path: Path | None,
        supplemental_summary: dict[str, dict[str, Any]],
        resolved_aoi: ResolvedAOI | None,
    ) -> tuple[Path, list[TileFusionArtifact], dict[str, Any]]:
        from services.domain_fusion_runners import run_water_polygon_tile, run_waterways_tile
        from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice

        water_sources: dict[str, Path] = {base_source_id: base_path}
        if supplement_path is not None and supplement_source_id is not None:
            water_sources[supplement_source_id] = supplement_path

        slices = [
            LargeAreaSlice(
                name="water_polygon",
                geometry_family="polygon",
                sources=water_sources,
                runner=run_water_polygon_tile,
            )
        ]
        waterways_path = self._supplemental_artifact_path(supplemental_summary, "raw.osm.waterways")
        line_supplement_source_id = (
            "raw.hydrorivers.water"
            if self._supplemental_artifact_path(supplemental_summary, "raw.hydrorivers.water") is not None
            else "raw.local.pakistan.waterways"
        )
        line_supplement_path = self._supplemental_artifact_path(supplemental_summary, line_supplement_source_id)
        if waterways_path is not None and line_supplement_path is not None:
            slices.append(
                LargeAreaSlice(
                    name="waterways_line",
                    geometry_family="line",
                    sources={
                        "raw.osm.waterways": waterways_path,
                        line_supplement_source_id: line_supplement_path,
                    },
                    runner=run_waterways_tile,
                    parameters={"profile": "balanced"},
                )
            )

        runtime_result = LargeAreaRuntimeService(max_workers=1).run(
            run_id="track-b-national-water",
            job_type="water",
            tile_manifest=tile_manifest,
            slices=slices,
            output_dir=output_root / "runtime_output" / "water_shared_runtime",
            target_crs=target_crs,
            parameters={},
            clip_boundary=None,
        )
        output_path = output_root / "water_national_scale_fused.gpkg"
        final_output = self._copy_and_clip_gpkg(
            runtime_result.output_path,
            output_path,
            target_crs=target_crs,
            clip_boundary=self._country_boundary_for_aoi(resolved_aoi, target_crs=target_crs),
        )
        tile_results = [
            TileFusionArtifact(
                tile_id=item.tile_id,
                output_path=item.output_path,
                feature_count=item.feature_count,
                working_bbox=item.working_bbox,
            )
            for item in runtime_result.tile_outputs
        ]
        algorithm_id = "algo.fusion.water_polygon.priority_merge.v2"
        stats = self._merge_runtime_stats(runtime_result.tile_outputs)
        config_snapshot = self._first_runtime_config(runtime_result.tile_outputs)
        self._write_fusion_stats(
            output_root=output_root,
            algorithm_id=algorithm_id,
            stats=stats,
            config_snapshot=config_snapshot,
        )
        fusion_summary = {
            "algorithm_id": algorithm_id,
            "config_snapshot": config_snapshot,
            "lineage": {
                "algorithm_id": algorithm_id,
                "base_source_id": base_source_id,
                "supplement_source_id": supplement_source_id,
                "line_source_ids": [
                    source_id
                    for source_id in ("raw.osm.waterways", line_supplement_source_id)
                    if self._supplemental_artifact_path(supplemental_summary, source_id) is not None
                ],
                "runtime": "shared_large_area_runtime",
                "runtime_evidence_paths": {
                    key: str(path) for key, path in runtime_result.evidence_paths.items()
                },
            },
            "stats": stats,
        }
        return final_output, tile_results, fusion_summary

    def _run_v7_national_line_fusion(
        self,
        *,
        theme: str,
        request_bbox: tuple[float, float, float, float],
        target_crs: str,
        output_root: Path,
        tile_manifest,
        base_source_id: str,
        base_path: Path,
        supplement_source_id: str | None,
        supplement_path: Path | None,
        base_frame: gpd.GeoDataFrame,
        supplement_frame: gpd.GeoDataFrame,
        resolved_aoi: ResolvedAOI | None,
    ) -> tuple[Path, list[TileFusionArtifact], dict[str, Any]]:
        if theme == "road":
            return self._run_road_national_large_area_fusion(
                tile_manifest=tile_manifest,
                target_crs=target_crs,
                output_root=output_root,
                base_source_id=base_source_id,
                base_path=base_path,
                supplement_source_id=supplement_source_id,
                supplement_path=supplement_path,
                resolved_aoi=resolved_aoi,
            )

        config = WaterwaysConflationV7Config(target_crs=target_crs)
        result = run_waterways_conflation_v7(base_frame, supplement_frame, config=config)

        fused = result.frame
        clip_boundary = self._country_boundary_for_aoi(resolved_aoi, target_crs=target_crs)
        if clip_boundary is not None and not clip_boundary.empty:
            fused = self._clip_frame_to_boundary(fused, clip_boundary=clip_boundary, target_crs=target_crs)
        output_path = self._write_gpkg(fused, output_root / f"{theme}_national_scale_fused.gpkg", target_crs=target_crs)
        self._write_fusion_stats(
            output_root=output_root,
            algorithm_id=result.lineage["algorithm_id"],
            stats=result.stats,
            config_snapshot=result.config,
        )
        tile_results = [
            TileFusionArtifact(
                tile_id="national",
                output_path=output_path,
                feature_count=int(len(fused.index)),
                working_bbox=request_bbox,
            )
        ]
        fusion_summary = {
            "algorithm_id": result.lineage["algorithm_id"],
            "config_snapshot": result.config,
            "lineage": result.lineage,
            "stats": result.stats,
        }
        return output_path, tile_results, fusion_summary

    def _run_road_national_large_area_fusion(
        self,
        *,
        tile_manifest,
        target_crs: str,
        output_root: Path,
        base_source_id: str,
        base_path: Path,
        supplement_source_id: str | None,
        supplement_path: Path | None,
        resolved_aoi: ResolvedAOI | None,
    ) -> tuple[Path, list[TileFusionArtifact], dict[str, Any]]:
        from services.domain_fusion_runners import run_road_tile
        from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice

        road_sources: dict[str, Path] = {"raw.osm.road": base_path}
        if supplement_path is not None and supplement_source_id is not None:
            road_sources["raw.overture.transportation"] = supplement_path

        runtime_result = LargeAreaRuntimeService(max_workers=1).run(
            run_id="track-b-national-road",
            job_type="road",
            tile_manifest=tile_manifest,
            slices=[
                LargeAreaSlice(
                    name="road",
                    geometry_family="line",
                    sources=road_sources,
                    runner=run_road_tile,
                    parameters={"profile": "balanced"},
                )
            ],
            output_dir=output_root / "runtime_output" / "road_shared_runtime",
            target_crs=target_crs,
            parameters={},
            clip_boundary=self._country_boundary_for_aoi(resolved_aoi, target_crs=target_crs),
        )
        output_path = output_root / "road_national_scale_fused.gpkg"
        final_output = self._copy_gpkg(runtime_result.output_path, output_path, target_crs=target_crs)
        tile_results = [
            TileFusionArtifact(
                tile_id=item.tile_id,
                output_path=item.output_path,
                feature_count=item.feature_count,
                working_bbox=item.working_bbox,
            )
            for item in runtime_result.tile_outputs
        ]
        algorithm_id = "algo.fusion.road.conflation.v7"
        stats = self._merge_runtime_stats(runtime_result.tile_outputs)
        config_snapshot = self._first_runtime_config(runtime_result.tile_outputs)
        self._write_fusion_stats(
            output_root=output_root,
            algorithm_id=algorithm_id,
            stats=stats,
            config_snapshot=config_snapshot,
        )
        fusion_summary = {
            "algorithm_id": algorithm_id,
            "config_snapshot": config_snapshot,
            "lineage": {
                "algorithm_id": algorithm_id,
                "base_source_id": base_source_id,
                "supplement_source_id": supplement_source_id,
                "runtime": "shared_large_area_runtime",
                "runtime_evidence_paths": {
                    key: str(path) for key, path in runtime_result.evidence_paths.items()
                },
            },
            "stats": stats,
        }
        return final_output, tile_results, fusion_summary

    @staticmethod
    def _coverage_path(coverage: object) -> Path | None:
        if isinstance(coverage, dict):
            raw = coverage.get("path") or coverage.get("artifact_path") or coverage.get("zip_path")
        else:
            raw = (
                getattr(coverage, "path", None)
                or getattr(coverage, "artifact_path", None)
                or getattr(coverage, "zip_path", None)
            )
        return Path(str(raw)) if raw else None

    @staticmethod
    def _coverage_source_mode(coverage: object) -> object:
        if isinstance(coverage, dict):
            return coverage.get("source_mode")
        return getattr(coverage, "source_mode", None)

    @staticmethod
    def _coverage_is_available(coverage: object) -> bool:
        if coverage is None:
            return False
        if isinstance(coverage, dict):
            coverage_status = coverage.get("coverage_status")
            feature_count = coverage.get("feature_count")
        else:
            coverage_status = getattr(coverage, "coverage_status", None)
            feature_count = getattr(coverage, "feature_count", None)
        if str(coverage_status or "").strip().lower() == "available":
            return True
        try:
            return int(feature_count or 0) > 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _raise_selected_poi_materialization_error(source_id: str, path: Path | None, reason: Exception | str) -> None:
        path_text = str(path) if path is not None else "<missing>"
        if isinstance(reason, Exception):
            detail = f"{type(reason).__name__}: {reason}"
        else:
            detail = str(reason)
        raise RuntimeError(f"Failed to materialize selected POI source {source_id}: {detail} path={path_text}")

    @staticmethod
    def _supplemental_artifact_path(
        supplemental_summary: dict[str, dict[str, Any]],
        source_id: str,
    ) -> Path | None:
        raw = supplemental_summary.get(source_id, {}).get("artifact_path")
        if not raw:
            return None
        path = Path(str(raw))
        return path if path.exists() else None

    def _building_vector_sources(
        self,
        *,
        selected_sources: dict[str, Path | None],
        supplemental_summary: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Path], dict[str, str]]:
        vector_sources: dict[str, Path] = {}
        source_id_by_alias: dict[str, str] = {}

        candidate_paths: dict[str, Path | None] = dict(selected_sources)
        for source_id, summary in supplemental_summary.items():
            raw_path = summary.get("artifact_path")
            candidate_paths[source_id] = Path(raw_path) if raw_path else None

        for source_id, artifact_path in candidate_paths.items():
            if artifact_path is None or not artifact_path.exists():
                continue
            if source_id == "raw.local.microsoft.building" and "raw.microsoft.building" in candidate_paths:
                continue
            alias = BUILDING_SOURCE_ALIASES.get(source_id)
            if not alias or alias in vector_sources:
                continue
            vector_sources[alias] = artifact_path
            source_id_by_alias[alias] = source_id
        return vector_sources, source_id_by_alias

    def _run_tile_fusion(
        self,
        *,
        theme: str,
        tile: TileSpec,
        osm_frame: gpd.GeoDataFrame,
        ref_frame: gpd.GeoDataFrame,
        supplemental_summary: dict[str, dict[str, Any]],
        target_crs: str,
        tile_dir: Path,
        poi_sources: dict[str, gpd.GeoDataFrame] | None = None,
    ) -> TileFusionArtifact:
        tile_dir.mkdir(parents=True, exist_ok=True)
        buffered = box(*tile.working_buffered_bbox)
        base_tile = osm_frame[osm_frame.geometry.intersects(buffered)].copy()
        ref_tile = ref_frame[ref_frame.geometry.intersects(buffered)].copy()

        if theme == "road":
            fused = run_road_conflation_v7(
                base_tile,
                ref_tile,
                config=RoadConflationV7Config(target_crs=target_crs, profile="balanced"),
            ).frame
        elif theme == "water":
            fused = fuse_water_polygons(base_tile, ref_tile)
        elif theme == "waterways":
            fused = run_waterways_conflation_v7(
                base_tile,
                ref_tile,
                config=WaterwaysConflationV7Config(target_crs=target_crs),
            ).frame
        else:
            sources = {}
            if poi_sources:
                for source_id in self._poi_component_source_ids(list(poi_sources.keys())):
                    alias = POI_SOURCE_ALIASES.get(source_id)
                    if alias is None:
                        continue
                    frame = poi_sources[source_id]
                    tile_frame = frame[frame.geometry.intersects(buffered)].copy()
                    if not tile_frame.empty:
                        sources[alias] = tile_frame
            else:
                if not ref_tile.empty:
                    sources["GNG"] = ref_tile
                if not base_tile.empty:
                    sources["OSM"] = base_tile
            if not sources:
                fused = _empty_frame(target_crs)
            else:
                source_priority_order = tuple(alias for alias in POI_SOURCE_PRIORITY_ORDER if alias in sources)
                fused = run_poi_geohash_priority_fusion(
                    sources,
                    PoiFusionParams(source_priority_order=source_priority_order),
                )

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
        clip_boundary: gpd.GeoDataFrame | None = None,
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
        if clip_boundary is not None and not clip_boundary.empty:
            combined = self._clip_frame_to_boundary(combined, clip_boundary=clip_boundary, target_crs=target_crs)
        return self._write_gpkg(combined, output_path, target_crs=target_crs)

    @staticmethod
    def _merge_runtime_stats(tile_outputs: list[Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for tile_output in tile_outputs:
            raw_stats = dict(getattr(tile_output, "stats", {}) or {})
            stats = raw_stats.get("stats")
            if not isinstance(stats, dict):
                continue
            for key, value in stats.items():
                if isinstance(value, bool):
                    merged[key] = int(merged.get(key, 0)) + int(value)
                elif isinstance(value, int):
                    merged[key] = int(merged.get(key, 0)) + value
                elif isinstance(value, float):
                    merged[key] = float(merged.get(key, 0.0)) + value
                elif key not in merged:
                    merged[key] = value
        return merged

    @staticmethod
    def _first_runtime_config(tile_outputs: list[Any]) -> dict[str, Any]:
        for tile_output in tile_outputs:
            raw_stats = dict(getattr(tile_output, "stats", {}) or {})
            config = raw_stats.get("config")
            if isinstance(config, dict):
                return config
        return {}

    @staticmethod
    def _evidence_tile_count(tile_results: list[TileFusionArtifact]) -> int:
        tile_ids = {item.tile_id for item in tile_results}
        return len(tile_ids) if tile_ids else 0

    def _copy_gpkg(self, source_path: Path, output_path: Path, *, target_crs: str) -> Path:
        frame = gpd.read_file(source_path)
        return self._write_gpkg(frame, output_path, target_crs=target_crs)

    def _copy_and_clip_gpkg(
        self,
        source_path: Path,
        output_path: Path,
        *,
        target_crs: str,
        clip_boundary: gpd.GeoDataFrame | None,
    ) -> Path:
        frame = gpd.read_file(source_path)
        if clip_boundary is not None and not clip_boundary.empty:
            frame = self._clip_frame_to_boundary(frame, clip_boundary=clip_boundary, target_crs=target_crs)
        return self._write_gpkg(frame, output_path, target_crs=target_crs)

    @staticmethod
    def _write_fusion_stats(
        *,
        output_root: Path,
        algorithm_id: str,
        stats: dict[str, Any],
        config_snapshot: dict[str, Any],
    ) -> None:
        (output_root / "fusion_stats.json").write_text(
            json.dumps(
                {
                    "algorithm_id": algorithm_id,
                    "stats": stats,
                    "config": config_snapshot,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _country_boundary_for_aoi(self, resolved_aoi: ResolvedAOI | None, *, target_crs: str) -> gpd.GeoDataFrame | None:
        if resolved_aoi is None:
            return None
        resolver = getattr(self.raw_source_service.source_asset_service, "resolve_country_boundary", None)
        if not callable(resolver):
            return None
        boundary = resolver(resolved_aoi)
        if boundary is None or boundary.empty:
            return None
        if boundary.crs is None:
            boundary = boundary.set_crs("EPSG:4326")
        return boundary.to_crs(target_crs)

    @staticmethod
    def _clip_frame_to_boundary(
        frame: gpd.GeoDataFrame,
        *,
        clip_boundary: gpd.GeoDataFrame,
        target_crs: str,
    ) -> gpd.GeoDataFrame:
        if frame.empty:
            return frame
        frame_ll = frame.to_crs("EPSG:4326")
        boundary_geom = clip_boundary.to_crs("EPSG:4326").geometry.iloc[0]
        clipped = frame_ll.copy()
        clipped["geometry"] = clipped.geometry.apply(
            lambda geom: geom.intersection(boundary_geom) if geom is not None and not geom.is_empty else geom
        )
        clipped = clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty].copy()
        if clipped.empty:
            return _empty_frame(target_crs)
        return clipped.to_crs(target_crs)

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


def _building_readiness_coverage(
    *,
    selected_coverage: dict[str, dict[str, Any]],
    supplemental_summary: dict[str, dict[str, Any]],
    road_summary: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    coverage = {source_id: dict(payload) for source_id, payload in selected_coverage.items()}
    for source_id, summary in supplemental_summary.items():
        payload = _readiness_payload_from_summary(source_id, summary)
        coverage.setdefault(source_id, payload)
    coverage["raw.osm.road"] = _readiness_payload_from_summary("raw.osm.road", road_summary)
    return coverage


def _readiness_payload_from_summary(source_id: str, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_mode": summary.get("source_mode"),
        "feature_count": summary.get("feature_count"),
        "coverage_status": summary.get("coverage_status"),
        "path": summary.get("artifact_path") or summary.get("path"),
        "error": summary.get("error"),
    }


def _write_autonomous_readiness(
    *,
    output_root: Path,
    job_type: str,
    component_coverage: dict[str, Any],
    source_attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    autonomous_readiness = classify_autonomous_readiness(
        job_type=job_type,
        component_coverage=component_coverage,
        source_attempts=source_attempts,
    )
    (output_root / "autonomous_readiness.json").write_text(
        json.dumps(autonomous_readiness, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return autonomous_readiness
