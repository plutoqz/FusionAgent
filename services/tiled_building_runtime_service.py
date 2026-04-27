from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import geopandas as gpd
import pandas as pd

from adapters.building_adapter import run_building_fusion_safe
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

    @staticmethod
    def _feature_count(path: Path) -> int:
        frame = gpd.read_file(path)
        return int(len(frame.index))

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
