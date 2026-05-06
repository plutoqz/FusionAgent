from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds
from shapely.geometry import box


DEFAULT_INPUT_GPKG = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\runtime_output\fused_buildings.gpkg")
DEFAULT_INPUT_LAYER = "fused_buildings"
DEFAULT_TILE_ROOT = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\runtime_output\tiles")
DEFAULT_TILE_MANIFEST = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\tile_manifest.json")
DEFAULT_VRT = Path(r"E:\fyx\data\Benin\google_open_buildings_temporal_2023\google_open_buildings_temporal_2023.vrt")
DEFAULT_OUTPUT_GPKG = Path(
    r"E:\fyx\data\Benin\final_shp\fusionbuildings\runtime_output\fused_buildings_height_enriched.gpkg"
)
DEFAULT_TMP_ROOT = Path(r"E:\fyx\data\Benin\final_shp\fusionbuildings\height_enrichment_tmp")
HEIGHT_COLUMNS = (
    "height_raster_max",
    "height_raster_min",
    "height_raster_centroid",
    "height_raster_dominant",
)


def _rasterio_env_kwargs() -> dict[str, str]:
    base_dir = Path(rasterio.__file__).resolve().parent
    kwargs: dict[str, str] = {}
    proj_data = base_dir / "proj_data"
    gdal_data = base_dir / "gdal_data"
    if proj_data.exists():
        kwargs["PROJ_DATA"] = str(proj_data)
        kwargs["PROJ_LIB"] = str(proj_data)
    if gdal_data.exists():
        kwargs["GDAL_DATA"] = str(gdal_data)
    return kwargs


@contextmanager
def managed_rasterio_env() -> Iterable[None]:
    env_kwargs = _rasterio_env_kwargs()
    previous_values = {key: os.environ.get(key) for key in env_kwargs}
    try:
        for key, value in env_kwargs.items():
            os.environ[key] = value
        with rasterio.Env(**env_kwargs):
            yield
    finally:
        for key, previous in previous_values.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


@dataclass(frozen=True)
class EnrichedTileArtifact:
    tile_id: str
    output_path: Path
    working_bbox: tuple[float, float, float, float]
    working_buffered_bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class TileJob:
    tile_id: str
    tile_input_path: Path
    tile_output_path: Path
    working_bbox: tuple[float, float, float, float]
    working_buffered_bbox: tuple[float, float, float, float]


def _quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _count_gpkg_features(path: Path, *, layer_name: str) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Missing GeoPackage: {path}")
    query = f"SELECT COUNT(*) FROM {_quote_sqlite_identifier(layer_name)}"
    with sqlite3.connect(path) as connection:
        count = connection.execute(query).fetchone()
    if count is None:
        raise ValueError(f"Unable to count features for layer '{layer_name}' in {path}")
    return int(count[0])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attach Google temporal raster height fields to fused Benin buildings")
    parser.add_argument("--input-gpkg", type=Path, default=DEFAULT_INPUT_GPKG)
    parser.add_argument("--input-layer", default=DEFAULT_INPUT_LAYER)
    parser.add_argument("--tile-root", type=Path, default=DEFAULT_TILE_ROOT)
    parser.add_argument("--tile-manifest", type=Path, default=DEFAULT_TILE_MANIFEST)
    parser.add_argument("--vrt", type=Path, default=DEFAULT_VRT)
    parser.add_argument("--height-band", type=int, default=2)
    parser.add_argument("--output-gpkg", type=Path, default=DEFAULT_OUTPUT_GPKG)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--subtile-size-m", type=float, default=2048.0)
    parser.add_argument("--tmp-root", type=Path, default=DEFAULT_TMP_ROOT)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--overwrite-output", action="store_true")
    return parser.parse_args()


def _coerce_bbox(values: Iterable[float]) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = values
    return (float(minx), float(miny), float(maxx), float(maxy))


def _intersect_bbox(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    minx = max(left[0], right[0])
    miny = max(left[1], right[1])
    maxx = min(left[2], right[2])
    maxy = min(left[3], right[3])
    if minx >= maxx or miny >= maxy:
        return None
    return (minx, miny, maxx, maxy)


def _iter_subtile_bounds(
    bbox: tuple[float, float, float, float],
    *,
    subtile_size_m: float,
) -> Iterable[tuple[float, float, float, float]]:
    minx, miny, maxx, maxy = bbox
    x = minx
    while x < maxx:
        next_x = min(maxx, x + subtile_size_m)
        y = miny
        while y < maxy:
            next_y = min(maxy, y + subtile_size_m)
            yield (x, y, next_x, next_y)
            y = next_y
        x = next_x


def _is_valid_height(value: float, nodata: float | None) -> bool:
    if not math.isfinite(value):
        return False
    if nodata is not None and math.isclose(value, float(nodata), rel_tol=0.0, abs_tol=1e-9):
        return False
    return value > 0.0


def _sample_centroid_heights(
    frame: gpd.GeoDataFrame,
    dataset: rasterio.io.DatasetReader,
    *,
    height_band: int,
) -> np.ndarray:
    result = np.full(len(frame), np.nan, dtype="float64")
    if frame.empty:
        return result

    valid_items: list[tuple[int, tuple[float, float]]] = []
    for idx, geom in enumerate(frame.geometry):
        if geom is None or geom.is_empty:
            continue
        centroid = geom.centroid
        if centroid.is_empty:
            continue
        valid_items.append((idx, (centroid.x, centroid.y)))

    if not valid_items:
        return result

    sample_indexes, coords = zip(*valid_items)
    for idx, sampled in zip(sample_indexes, dataset.sample(coords, indexes=height_band)):
        value = float(sampled[0]) if len(sampled) else float("nan")
        if _is_valid_height(value, dataset.nodata):
            result[idx] = round(value, 3)
    return result


def compute_tile_height_metrics(
    buildings: gpd.GeoDataFrame,
    raster_path: Path,
    *,
    height_band: int,
    processing_bbox: tuple[float, float, float, float] | None,
    subtile_size_m: float,
) -> gpd.GeoDataFrame:
    output = buildings.copy()
    for column in HEIGHT_COLUMNS:
        output[column] = pd.Series(np.full(len(output), np.nan, dtype="float64"), index=output.index)
    if output.empty:
        return output

    with managed_rasterio_env(), rasterio.open(raster_path) as dataset:
        processing = output
        if processing.crs is None:
            processing = processing.set_crs(dataset.crs)
        elif dataset.crs is not None and processing.crs != dataset.crs:
            processing = processing.to_crs(dataset.crs)

        raster_bounds = (
            float(dataset.bounds.left),
            float(dataset.bounds.bottom),
            float(dataset.bounds.right),
            float(dataset.bounds.top),
        )
        effective_bbox = processing_bbox or _coerce_bbox(processing.total_bounds)
        clipped_bbox = _intersect_bbox(_coerce_bbox(effective_bbox), raster_bounds)
        if clipped_bbox is None:
            return output

        output["height_raster_centroid"] = _sample_centroid_heights(processing, dataset, height_band=height_band)
        min_values = np.full(len(output), np.nan, dtype="float64")
        max_values = np.full(len(output), np.nan, dtype="float64")
        dominant_counts: dict[int, dict[float, int]] = defaultdict(dict)

        spatial_index = processing.sindex
        for subtile_bbox in _iter_subtile_bounds(clipped_bbox, subtile_size_m=subtile_size_m):
            candidate_positions = list(spatial_index.intersection(subtile_bbox))
            if not candidate_positions:
                continue

            subtile_box = box(*subtile_bbox)
            candidates = processing.iloc[candidate_positions]
            candidates = candidates[candidates.geometry.notna() & ~candidates.geometry.is_empty].copy()
            candidates = candidates[candidates.geometry.intersects(subtile_box)].copy()
            if candidates.empty:
                continue

            window = from_bounds(*subtile_bbox, transform=dataset.transform)
            window = window.round_offsets().round_lengths()
            if int(window.width) <= 0 or int(window.height) <= 0:
                continue

            band = dataset.read(height_band, window=window, masked=True)
            if band.size == 0:
                continue

            local_transform = dataset.window_transform(window)
            local_positions = candidates.index.to_list()
            local_ids = np.arange(1, len(local_positions) + 1, dtype="int32")
            id_grid = rasterize(
                shapes=zip(candidates.geometry, local_ids),
                out_shape=band.shape,
                transform=local_transform,
                fill=0,
                dtype="int32",
                all_touched=False,
            )

            data = np.asarray(band.data, dtype="float64")
            valid_mask = np.isfinite(data) & ~np.ma.getmaskarray(band) & (id_grid > 0) & (data > 0.0)
            if dataset.nodata is not None:
                valid_mask &= data != float(dataset.nodata)
            if not np.any(valid_mask):
                continue

            pixel_local_ids = id_grid[valid_mask] - 1
            pixel_values = np.round(data[valid_mask], 3)
            order = np.argsort(pixel_local_ids, kind="stable")
            pixel_local_ids = pixel_local_ids[order]
            pixel_values = pixel_values[order]
            unique_ids, starts = np.unique(pixel_local_ids, return_index=True)

            for group_idx, start in enumerate(starts):
                stop = starts[group_idx + 1] if group_idx + 1 < len(starts) else len(pixel_local_ids)
                values = pixel_values[start:stop]
                if values.size == 0:
                    continue
                output_pos = local_positions[int(unique_ids[group_idx])]
                group_min = float(values.min())
                group_max = float(values.max())
                if np.isnan(min_values[output_pos]) or group_min < min_values[output_pos]:
                    min_values[output_pos] = group_min
                if np.isnan(max_values[output_pos]) or group_max > max_values[output_pos]:
                    max_values[output_pos] = group_max

                uniq_values, counts = np.unique(values, return_counts=True)
                counter = dominant_counts[output_pos]
                for value, count in zip(uniq_values, counts):
                    numeric = float(value)
                    counter[numeric] = counter.get(numeric, 0) + int(count)

        output["height_raster_min"] = min_values
        output["height_raster_max"] = max_values

        dominant_values = np.full(len(output), np.nan, dtype="float64")
        for idx, counter in dominant_counts.items():
            best_count = max(counter.values())
            best_values = [value for value, count in counter.items() if count == best_count]
            dominant_values[idx] = max(best_values)
        output["height_raster_dominant"] = dominant_values

    return output


def enrich_tile_gpkg(
    *,
    tile_input_path: Path,
    tile_output_path: Path,
    vrt_path: Path,
    height_band: int,
    working_buffered_bbox: tuple[float, float, float, float],
    subtile_size_m: float,
    target_crs: str,
    layer_name: str = DEFAULT_INPUT_LAYER,
) -> Path:
    frame = gpd.read_file(tile_input_path, layer=layer_name)
    enriched = compute_tile_height_metrics(
        frame,
        vrt_path,
        height_band=height_band,
        processing_bbox=working_buffered_bbox,
        subtile_size_m=subtile_size_m,
    )
    if enriched.crs is None:
        enriched = enriched.set_crs(target_crs)
    else:
        enriched = enriched.to_crs(target_crs)
    tile_output_path.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_file(tile_output_path, driver="GPKG", layer=layer_name)
    return tile_output_path


def stitch_enriched_tiles(
    tile_artifacts: list[EnrichedTileArtifact],
    output_path: Path,
    *,
    target_crs: str,
    layer_name: str = DEFAULT_INPUT_LAYER,
) -> Path:
    frames: list[gpd.GeoDataFrame] = []
    for artifact in tile_artifacts:
        frame = gpd.read_file(artifact.output_path, layer=layer_name)
        if frame.empty:
            continue
        if frame.crs is None:
            frame = frame.set_crs(target_crs)
        else:
            frame = frame.to_crs(target_crs)
        frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
        if frame.empty:
            continue
        owner_box = box(*artifact.working_bbox)
        owner_mask = frame.geometry.representative_point().apply(owner_box.covers)
        frame = frame[owner_mask].copy()
        if frame.empty:
            continue
        frame["_tile_id"] = artifact.tile_id
        frames.append(frame)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not frames:
        raise ValueError("No enriched tile frames were available for stitching.")

    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=target_crs)
    combined["_geometry_wkb"] = combined.geometry.apply(lambda geom: geom.wkb_hex if geom is not None else None)
    combined = combined.drop_duplicates(subset=["_geometry_wkb"], keep="first").copy()
    combined = combined.drop(columns=["_geometry_wkb", "_tile_id"], errors="ignore")
    combined.to_file(output_path, driver="GPKG", layer=layer_name)
    return output_path


def _load_tile_jobs(
    *,
    tile_root: Path,
    tile_manifest_path: Path,
    tmp_root: Path,
) -> list[TileJob]:
    manifest = json.loads(tile_manifest_path.read_text(encoding="utf-8"))
    jobs: list[TileJob] = []
    for tile in manifest["tiles"]:
        tile_id = str(tile["tile_id"])
        tile_input_path = tile_root / tile_id / "fused_buildings.gpkg"
        tile_output_path = tmp_root / "tiles" / tile_id / "fused_buildings_height.gpkg"
        jobs.append(
            TileJob(
                tile_id=tile_id,
                tile_input_path=tile_input_path,
                tile_output_path=tile_output_path,
                working_bbox=_coerce_bbox(tile["working_bbox"]),
                working_buffered_bbox=_coerce_bbox(tile["working_buffered_bbox"]),
            )
        )
    return jobs


def _run_tile_job(
    job: TileJob,
    *,
    vrt_path: Path,
    height_band: int,
    subtile_size_m: float,
    target_crs: str,
    resume: bool,
    layer_name: str,
) -> EnrichedTileArtifact:
    if resume and job.tile_output_path.exists():
        return EnrichedTileArtifact(
            tile_id=job.tile_id,
            output_path=job.tile_output_path,
            working_bbox=job.working_bbox,
            working_buffered_bbox=job.working_buffered_bbox,
        )
    if not job.tile_input_path.exists():
        raise FileNotFoundError(f"Missing tile input GPKG: {job.tile_input_path}")

    enrich_tile_gpkg(
        tile_input_path=job.tile_input_path,
        tile_output_path=job.tile_output_path,
        vrt_path=vrt_path,
        height_band=height_band,
        working_buffered_bbox=job.working_buffered_bbox,
        subtile_size_m=subtile_size_m,
        target_crs=target_crs,
        layer_name=layer_name,
    )
    return EnrichedTileArtifact(
        tile_id=job.tile_id,
        output_path=job.tile_output_path,
        working_bbox=job.working_bbox,
        working_buffered_bbox=job.working_buffered_bbox,
    )


def run_height_enrichment(
    *,
    input_gpkg: Path,
    input_layer: str,
    tile_root: Path,
    tile_manifest_path: Path,
    vrt_path: Path,
    height_band: int,
    output_gpkg: Path,
    tmp_root: Path,
    workers: int,
    subtile_size_m: float,
    resume: bool,
    overwrite_output: bool,
) -> Path:
    if output_gpkg.exists() and not overwrite_output:
        raise FileExistsError(f"Output already exists: {output_gpkg}")
    if output_gpkg.exists() and overwrite_output:
        output_gpkg.unlink()

    input_feature_count = _count_gpkg_features(input_gpkg, layer_name=input_layer)
    jobs = _load_tile_jobs(tile_root=tile_root, tile_manifest_path=tile_manifest_path, tmp_root=tmp_root)
    if not jobs:
        raise ValueError("Tile manifest did not contain any tile jobs.")

    with managed_rasterio_env(), rasterio.open(vrt_path) as dataset:
        target_crs = str(dataset.crs)

    artifacts: list[EnrichedTileArtifact] = []
    with ProcessPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = [
            executor.submit(
                _run_tile_job,
                job,
                vrt_path=vrt_path,
                height_band=height_band,
                subtile_size_m=subtile_size_m,
                target_crs=target_crs,
                resume=resume,
                layer_name=input_layer,
            )
            for job in jobs
        ]
        for future in futures:
            artifacts.append(future.result())

    artifacts.sort(key=lambda item: item.tile_id)
    stitched_output = stitch_enriched_tiles(
        artifacts,
        output_gpkg,
        target_crs=target_crs,
        layer_name=input_layer,
    )
    output_feature_count = _count_gpkg_features(stitched_output, layer_name=input_layer)
    if output_feature_count != input_feature_count:
        raise ValueError(
            "Stitched enriched output feature count does not match input feature count: "
            f"{output_feature_count} != {input_feature_count}"
        )
    return stitched_output


def main() -> None:
    args = _parse_args()
    run_height_enrichment(
        input_gpkg=args.input_gpkg,
        input_layer=args.input_layer,
        tile_root=args.tile_root,
        tile_manifest_path=args.tile_manifest,
        vrt_path=args.vrt,
        height_band=args.height_band,
        output_gpkg=args.output_gpkg,
        tmp_root=args.tmp_root,
        workers=args.workers,
        subtile_size_m=args.subtile_size_m,
        resume=args.resume,
        overwrite_output=args.overwrite_output,
    )


if __name__ == "__main__":
    main()
