from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from adapters.building_adapter import run_building_fusion_safe
from fusion_algorithms.building_height import attach_source_heights_and_final
from fusion_algorithms.building_matching_v8 import run_cascaded_multi_source_fusion
from fusion_algorithms.building_raster import enrich_height_from_raster, validate_presence_from_raster
from fusion_algorithms.contracts import (
    BuildingHeightParams,
    BuildingMatchParams,
    BuildingRasterPresenceParams,
    RasterSpec,
    params_from_mapping,
)
from services.tile_partition_service import TileManifest, TileSpec
from utils.shp_zip import validate_zip_has_shapefile


TileBundleFactory = Callable[[TileSpec, Path], Path]
TileEventCallback = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class TileRunArtifact:
    tile_id: str
    output_shp: Path
    feature_count: int
    bbox: tuple[float, float, float, float]
    buffered_bbox: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["output_shp"] = str(self.output_shp)
        return payload


@dataclass(frozen=True)
class TiledBuildingRunResult:
    output_shp: Path
    tile_count: int
    stitched_feature_count: int
    tile_outputs: list[TileRunArtifact] = field(default_factory=list)


@dataclass(frozen=True)
class MultiSourceTileRunArtifact:
    tile_id: str
    output_path: Path
    feature_count: int
    bbox: tuple[float, float, float, float]
    buffered_bbox: tuple[float, float, float, float]
    working_bbox: tuple[float, float, float, float]
    working_buffered_bbox: tuple[float, float, float, float]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["output_path"] = str(self.output_path)
        return payload


@dataclass(frozen=True)
class TiledMultiSourceBuildingRunResult:
    output_path: Path
    tile_count: int
    stitched_feature_count: int
    tile_outputs: list[MultiSourceTileRunArtifact] = field(default_factory=list)


class TiledBuildingRuntimeService:
    def __init__(self, *, max_workers: int = 2) -> None:
        self.max_workers = max(1, int(max_workers))

    def run_tiled_building_job(
        self,
        *,
        run_id: str,
        tile_manifest: TileManifest,
        osm_bundle_factory: TileBundleFactory,
        ref_bundle_factory: TileBundleFactory,
        output_dir: Path,
        target_crs: str,
        field_mapping: Optional[dict[str, dict[str, str]]] = None,
        debug: bool = False,
        parameters: Optional[dict[str, object]] = None,
        on_event: TileEventCallback | None = None,
    ) -> TiledBuildingRunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        tile_output_dir = output_dir / "tiles"
        tile_output_dir.mkdir(parents=True, exist_ok=True)

        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="building-tile") as pool:
            futures = [
                pool.submit(
                    self._run_tile,
                    run_id=run_id,
                    tile=tile,
                    tile_output_dir=tile_output_dir,
                    osm_bundle_factory=osm_bundle_factory,
                    ref_bundle_factory=ref_bundle_factory,
                    target_crs=target_crs,
                    field_mapping=field_mapping,
                    debug=debug,
                    parameters=parameters,
                    on_event=on_event,
                )
                for tile in tile_manifest.tiles
            ]
            tile_results = [future.result() for future in futures]

        tile_results.sort(key=lambda item: item.tile_id)
        stitched_shp = self._stitch_tile_outputs(
            tile_results=tile_results,
            output_shp=output_dir / "fused_buildings.shp",
            target_crs=target_crs,
        )
        stitched_feature_count = self._feature_count(stitched_shp)
        if on_event is not None:
            on_event(
                "tile_stitch_completed",
                {
                    "tile_count": len(tile_results),
                    "stitched_feature_count": stitched_feature_count,
                    "output_shp": str(stitched_shp),
                },
            )
        return TiledBuildingRunResult(
            output_shp=stitched_shp,
            tile_count=len(tile_results),
            stitched_feature_count=stitched_feature_count,
            tile_outputs=tile_results,
        )

    def run_tiled_multisource_building_job(
        self,
        *,
        run_id: str,
        tile_manifest: TileManifest,
        vector_sources: dict[str, Path],
        output_dir: Path,
        target_crs: str,
        raster_sources: Optional[dict[str, Path]] = None,
        context_vectors: Optional[dict[str, Path]] = None,
        source_priority_order: tuple[str, ...] | None = None,
        parameters: Optional[dict[str, object]] = None,
        on_event: TileEventCallback | None = None,
    ) -> TiledMultiSourceBuildingRunResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        tile_output_dir = output_dir / "tiles"
        tile_output_dir.mkdir(parents=True, exist_ok=True)
        ordered_sources = self._ordered_sources(vector_sources, source_priority_order)

        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="building-multisource-tile") as pool:
            futures = [
                pool.submit(
                    self._run_multisource_tile,
                    run_id=run_id,
                    tile=tile,
                    tile_output_dir=tile_output_dir,
                    vector_sources=ordered_sources,
                    raster_sources=raster_sources or {},
                    context_vectors=context_vectors or {},
                    target_crs=target_crs,
                    source_crs=tile_manifest.bbox_crs,
                    parameters=parameters,
                    on_event=on_event,
                )
                for tile in tile_manifest.tiles
            ]
            tile_results = [future.result() for future in futures]

        tile_results.sort(key=lambda item: item.tile_id)
        stitched_path = self._stitch_multisource_tile_outputs(
            tile_results=tile_results,
            output_path=output_dir / "fused_buildings.gpkg",
            target_crs=target_crs,
        )
        stitched_feature_count = self._feature_count(stitched_path)
        if on_event is not None:
            on_event(
                "tile_stitch_completed",
                {
                    "tile_count": len(tile_results),
                    "stitched_feature_count": stitched_feature_count,
                    "output_path": str(stitched_path),
                },
            )
        return TiledMultiSourceBuildingRunResult(
            output_path=stitched_path,
            tile_count=len(tile_results),
            stitched_feature_count=stitched_feature_count,
            tile_outputs=tile_results,
        )

    def _run_tile(
        self,
        *,
        run_id: str,
        tile: TileSpec,
        tile_output_dir: Path,
        osm_bundle_factory: TileBundleFactory,
        ref_bundle_factory: TileBundleFactory,
        target_crs: str,
        field_mapping: Optional[dict[str, dict[str, str]]],
        debug: bool,
        parameters: Optional[dict[str, object]],
        on_event: TileEventCallback | None,
    ) -> TileRunArtifact:
        tile_dir = tile_output_dir / tile.tile_id
        tile_dir.mkdir(parents=True, exist_ok=True)
        osm_zip_path = tile_dir / "osm.zip"
        ref_zip_path = tile_dir / "ref.zip"

        if on_event is not None:
            on_event(
                "tile_execution_started",
                {
                    "run_id": run_id,
                    "tile_id": tile.tile_id,
                    "bbox": list(tile.bbox),
                    "buffered_bbox": list(tile.buffered_bbox),
                },
            )

        osm_zip = osm_bundle_factory(tile, osm_zip_path)
        ref_zip = ref_bundle_factory(tile, ref_zip_path)
        osm_shp = validate_zip_has_shapefile(osm_zip, tile_dir / "osm_extract")
        ref_shp = validate_zip_has_shapefile(ref_zip, tile_dir / "ref_extract")

        output_shp = self._run_tile_fusion(
            osm_shp=osm_shp,
            ref_shp=ref_shp,
            tile_output_dir=tile_dir / "output",
            target_crs=target_crs,
            field_mapping=field_mapping,
            debug=debug,
            parameters=parameters,
        )
        feature_count = self._feature_count(output_shp)
        if on_event is not None:
            on_event(
                "tile_execution_completed",
                {
                    "run_id": run_id,
                    "tile_id": tile.tile_id,
                    "feature_count": feature_count,
                    "output_shp": str(output_shp),
                },
            )
        return TileRunArtifact(
            tile_id=tile.tile_id,
            output_shp=output_shp,
            feature_count=feature_count,
            bbox=tile.bbox,
            buffered_bbox=tile.buffered_bbox,
        )

    def _run_multisource_tile(
        self,
        *,
        run_id: str,
        tile: TileSpec,
        tile_output_dir: Path,
        vector_sources: dict[str, Path],
        raster_sources: dict[str, Path],
        context_vectors: dict[str, Path],
        target_crs: str,
        source_crs: str,
        parameters: Optional[dict[str, object]],
        on_event: TileEventCallback | None,
    ) -> MultiSourceTileRunArtifact:
        tile_dir = tile_output_dir / tile.tile_id
        tile_dir.mkdir(parents=True, exist_ok=True)
        if on_event is not None:
            on_event(
                "tile_execution_started",
                {
                    "run_id": run_id,
                    "tile_id": tile.tile_id,
                    "bbox": list(tile.bbox),
                    "buffered_bbox": list(tile.buffered_bbox),
                },
            )

        source_map = {
            name: self._read_vector_tile(path, tile=tile, source_crs=source_crs, target_crs=target_crs)
            for name, path in vector_sources.items()
        }
        source_map = {name: frame for name, frame in source_map.items() if not frame.empty}
        output_path = tile_dir / "fused_buildings.gpkg"
        if source_map:
            fused = self._run_multisource_tile_fusion(
                source_map=source_map,
                raster_sources=raster_sources,
                context_vectors=context_vectors,
                tile=tile,
                target_crs=target_crs,
                parameters=parameters,
            )
            self._write_gpkg(fused, output_path, target_crs=target_crs)
        else:
            self._write_empty_multisource_output(output_path, target_crs=target_crs)

        feature_count = self._feature_count(output_path)
        if on_event is not None:
            on_event(
                "tile_execution_completed",
                {
                    "run_id": run_id,
                    "tile_id": tile.tile_id,
                    "feature_count": feature_count,
                    "output_path": str(output_path),
                },
            )
        return MultiSourceTileRunArtifact(
            tile_id=tile.tile_id,
            output_path=output_path,
            feature_count=feature_count,
            bbox=tile.bbox,
            buffered_bbox=tile.buffered_bbox,
            working_bbox=tile.working_bbox,
            working_buffered_bbox=tile.working_buffered_bbox,
        )

    def _run_multisource_tile_fusion(
        self,
        *,
        source_map: dict[str, gpd.GeoDataFrame],
        raster_sources: dict[str, Path],
        context_vectors: dict[str, Path],
        tile: TileSpec,
        target_crs: str,
        parameters: Optional[dict[str, object]],
    ) -> gpd.GeoDataFrame:
        values = dict(parameters or {})
        presence_params = params_from_mapping(BuildingRasterPresenceParams, values)
        height_params = params_from_mapping(BuildingHeightParams, values)
        match_params = params_from_mapping(BuildingMatchParams, values)

        presence_path = raster_sources.get("building_presence")
        if presence_path is not None and Path(presence_path).exists():
            source_map = {
                name: validate_presence_from_raster(
                    frame,
                    RasterSpec(kind="building_presence", path=presence_path),
                    presence_params,
                )
                for name, frame in source_map.items()
            }

        roads = None
        road_path = context_vectors.get("roads")
        if road_path is not None and Path(road_path).exists():
            roads = self._read_vector_tile(road_path, tile=tile, source_crs=target_crs, target_crs=target_crs)

        if len(source_map) >= 2:
            order = tuple(source_map.keys())
            fused = run_cascaded_multi_source_fusion(
                source_map,
                roads,
                match_params,
                source_priority_order=order,
            )
        else:
            name, frame = next(iter(source_map.items()))
            fused = frame.copy()
            fused["fusion_runtime_mode"] = "single_source_tile"
            fused["fusion_source"] = name

        fused = attach_source_heights_and_final(fused, source_map, height_params)
        height_path = raster_sources.get("building_height")
        if height_path is not None and Path(height_path).exists():
            fused = enrich_height_from_raster(
                fused,
                RasterSpec(kind="building_height", path=height_path),
                height_params,
            )
        if fused.crs is None:
            fused = fused.set_crs(target_crs)
        else:
            fused = fused.to_crs(target_crs)
        return fused

    def _run_tile_fusion(
        self,
        *,
        osm_shp: Path,
        ref_shp: Path,
        tile_output_dir: Path,
        target_crs: str,
        field_mapping: Optional[dict[str, dict[str, str]]],
        debug: bool,
        parameters: Optional[dict[str, object]],
    ) -> Path:
        osm_frame = gpd.read_file(osm_shp)
        ref_frame = gpd.read_file(ref_shp)
        if osm_frame.empty and ref_frame.empty:
            return self._write_empty_building_output(tile_output_dir / "fused_buildings.shp", target_crs=target_crs)
        return run_building_fusion_safe(
            osm_shp=osm_shp,
            ref_shp=ref_shp,
            output_dir=tile_output_dir,
            target_crs=target_crs,
            field_mapping=field_mapping,
            debug=debug,
            parameters=parameters,
        )

    def _stitch_tile_outputs(
        self,
        *,
        tile_results: list[TileRunArtifact],
        output_shp: Path,
        target_crs: str,
    ) -> Path:
        frames: list[gpd.GeoDataFrame] = []
        for tile_result in tile_results:
            frame = gpd.read_file(tile_result.output_shp)
            if frame.empty:
                continue
            if frame.crs is None:
                frame = frame.set_crs(target_crs)
            else:
                frame = frame.to_crs(target_crs)
            frame = frame[~frame.geometry.is_empty & frame.geometry.notna()].copy()
            if frame.empty:
                continue
            frame["_tile_id"] = tile_result.tile_id
            frames.append(frame)

        output_shp.parent.mkdir(parents=True, exist_ok=True)
        if not frames:
            return self._write_empty_building_output(output_shp, target_crs=target_crs)

        combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
        combined["_geometry_wkb"] = combined.geometry.apply(lambda geom: geom.wkb_hex if geom is not None else None)
        combined = combined.drop_duplicates(subset=["_geometry_wkb"], keep="first").copy()
        combined = combined.drop(columns=["_geometry_wkb", "_tile_id"], errors="ignore")
        combined.to_file(output_shp)
        return output_shp

    def _stitch_multisource_tile_outputs(
        self,
        *,
        tile_results: list[MultiSourceTileRunArtifact],
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
            frame = frame[~frame.geometry.is_empty & frame.geometry.notna()].copy()
            if frame.empty:
                continue
            tile_box = box(*tile_result.working_bbox)
            owner_mask = frame.geometry.representative_point().apply(tile_box.covers)
            frame = frame[owner_mask].copy()
            if frame.empty:
                continue
            frame["_tile_id"] = tile_result.tile_id
            frames.append(frame)

        if not frames:
            return self._write_empty_multisource_output(output_path, target_crs=target_crs)

        combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
        combined["_geometry_wkb"] = combined.geometry.apply(lambda geom: geom.wkb_hex if geom is not None else None)
        combined = combined.drop_duplicates(subset=["_geometry_wkb"], keep="first").copy()
        combined = combined.drop(columns=["_geometry_wkb", "_tile_id"], errors="ignore")
        return self._write_gpkg(combined, output_path, target_crs=target_crs)

    @staticmethod
    def _ordered_sources(
        vector_sources: dict[str, Path],
        source_priority_order: tuple[str, ...] | None,
    ) -> dict[str, Path]:
        if not source_priority_order:
            return dict(vector_sources)
        ordered: dict[str, Path] = {}
        for name in source_priority_order:
            if name in vector_sources:
                ordered[name] = vector_sources[name]
        for name, path in vector_sources.items():
            if name not in ordered:
                ordered[name] = path
        return ordered

    @staticmethod
    def _read_vector_tile(
        path: Path,
        *,
        tile: TileSpec,
        source_crs: str,
        target_crs: str,
    ) -> gpd.GeoDataFrame:
        frame = gpd.read_file(path, bbox=tile.buffered_bbox)
        if frame.empty:
            return gpd.GeoDataFrame(geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs), crs=target_crs)
        if frame.crs is None:
            frame = frame.set_crs(source_crs)
        frame = frame.to_crs(target_crs)
        tile_box = box(*tile.working_buffered_bbox)
        frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
        return frame[frame.geometry.intersects(tile_box)].copy()

    @staticmethod
    def _write_gpkg(gdf: gpd.GeoDataFrame, output_path: Path, *, target_crs: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        frame = gdf.copy()
        if frame.crs is None:
            frame = frame.set_crs(target_crs)
        else:
            frame = frame.to_crs(target_crs)
        frame.to_file(output_path, driver="GPKG")
        return output_path

    @staticmethod
    def _feature_count(path: Path) -> int:
        frame = gpd.read_file(path)
        return int(len(frame.index))

    @staticmethod
    def _write_empty_multisource_output(output_path: Path, *, target_crs: str) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        empty = gpd.GeoDataFrame(
            {
                "fusion_source": pd.Series(dtype="object"),
                "height_osm": pd.Series(dtype="float64"),
                "height_ms": pd.Series(dtype="float64"),
                "height_google": pd.Series(dtype="float64"),
                "height_obm": pd.Series(dtype="float64"),
                "height_raster": pd.Series(dtype="float64"),
                "height_vector_fused": pd.Series(dtype="float64"),
                "height_final": pd.Series(dtype="float64"),
                "height_final_source": pd.Series(dtype="object"),
            },
            geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs),
            crs=target_crs,
        )
        empty.to_file(output_path, driver="GPKG")
        return output_path

    @staticmethod
    def _write_empty_building_output(output_shp: Path, *, target_crs: str) -> Path:
        output_shp.parent.mkdir(parents=True, exist_ok=True)
        empty = gpd.GeoDataFrame(
            {
                "osm_id": pd.Series(dtype="float64"),
                "fclass": pd.Series(dtype="object"),
                "name": pd.Series(dtype="object"),
                "type": pd.Series(dtype="object"),
                "longitude": pd.Series(dtype="float64"),
                "latitude": pd.Series(dtype="float64"),
                "area_in_me": pd.Series(dtype="float64"),
                "confidence": pd.Series(dtype="float64"),
            },
            geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs),
            crs=target_crs,
        )
        empty.to_file(output_shp)
        return output_shp
