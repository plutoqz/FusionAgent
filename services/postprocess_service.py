from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely import affinity


OUTPUT_CRS = "EPSG:4326"

STANDARD_FIELDS: dict[str, list[str]] = {
    "roads": [
        "fclass",
        "osm_id",
        "osm_old",
        "osm_uid",
        "source_layer",
        "label1",
        "label2",
        "label3",
        "original_FID_1",
        "msft_uid",
        "FID_1",
        "residual_from_matched",
        "residual_part",
        "residual_parent_FID_1",
    ],
    "waterways": [
        "fusion_source",
        "match_role",
        "matched_supplement_high",
        "matched_supplement_loose",
        "supplement_segment_id",
        "matched_base_segment_id",
        "waterway_class",
        "name",
        "name_en",
        "name_ur",
        "width",
        "depth",
        "covered",
        "layer",
        "blockage",
        "tunnel",
        "natural",
        "water",
        "supplement_source",
        "osm_old",
        "osm_id",
        "osm_type",
        "source_layer",
        "label1",
        "label2",
        "label3",
        "msft_uid",
        "original_FID_1",
        "residual_from_matched",
        "residual_part",
        "residual_parent_FID_1",
    ],
    "lakes": [
        "fusion_source",
        "match_role",
        "osm_lake_id",
        "osm_id",
        "fclass",
        "name",
        "matched_lakeatlas_uid",
        "matched_hylak_id",
        "match_count",
        "max_overlap_osm_ratio",
        "max_overlap_lakeatlas_ratio",
        "lakeatlas_uid",
        "Hylak_id",
        "atlas_Lake_name",
        "atlas_Lake_type",
        "atlas_Lake_area",
        "atlas_Depth_avg",
        "atlas_Vol_total",
        "atlas_Res_time",
        "atlas_Elevation",
        "atlas_Pour_long",
        "atlas_Pour_lat",
        "code",
        "osm_area_m2",
        "atlas_Grand_id",
        "atlas_Shore_len",
        "atlas_Vol_res",
        "atlas_Dis_avg",
        "atlas_Wshd_area",
    ],
    "poi": [
        "id",
        "name",
        "alternaten",
        "lat",
        "lon",
        "type",
        "type_intro",
        "region",
        "population",
        "elevation",
        "dem",
        "source",
        "sourceid",
        "modifydate",
    ],
    "buildings": [
        "source",
        "Height",
        "H_Raster",
        "wzp_score",
        "avg_prob",
        "exist_stat",
        "match_rel",
        "opt_dx",
        "opt_dy",
        "opt_ds",
        "Occupancy_type",
        "type",
        "name",
        "is_toll",
    ],
}


@dataclass(frozen=True)
class CountryPostprocessConfig:
    key: str
    label: str
    training_dir: Path
    clip_name: str
    target_crs: str

    @property
    def fusion_dir(self) -> Path:
        return self.training_dir / "融合"

    @property
    def clip_gpkg(self) -> Path:
        return self.training_dir / self.clip_name


COUNTRY_CONFIGS: dict[str, CountryPostprocessConfig] = {
    "mongolia": CountryPostprocessConfig(
        key="mongolia",
        label="蒙古",
        training_dir=Path(r"E:\fyx\data\蒙古\培训文件夹"),
        clip_name="mongolia_capital_government_clip.gpkg",
        target_crs="EPSG:32648",
    ),
    "nepal": CountryPostprocessConfig(
        key="nepal",
        label="尼泊尔",
        training_dir=Path(r"E:\fyx\data\尼泊尔\培训文件夹"),
        clip_name="nepal_capital_government_clip.gpkg",
        target_crs="EPSG:32645",
    ),
}


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


def _valid_height(value: Any) -> bool:
    try:
        height = float(value)
    except (TypeError, ValueError):
        return False
    return height > 0


def _as_numeric(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _first_existing(row: pd.Series, columns: tuple[str, ...]) -> Any:
    for column in columns:
        if column in row.index and pd.notna(row[column]) and str(row[column]).strip():
            return row[column]
    return None


def _standardize_columns(frame: gpd.GeoDataFrame, domain: str) -> gpd.GeoDataFrame:
    fields = STANDARD_FIELDS[domain]
    result = frame.copy()
    if domain == "buildings":
        if "source" not in result.columns:
            result["source"] = result.apply(
                lambda row: _first_existing(row, ("src_flag", "fusion_lineage", "source_layer")) or "fusion",
                axis=1,
            )
        if "Height" not in result.columns:
            result["Height"] = result.get("height_fused", pd.Series([None] * len(result), index=result.index))
        if "H_Raster" not in result.columns:
            result["H_Raster"] = result.get("height_fused", pd.Series([None] * len(result), index=result.index))
        if "match_rel" not in result.columns:
            result["match_rel"] = result.get("rel_type", pd.Series([None] * len(result), index=result.index))
        if "name" not in result.columns:
            result["name"] = result.get("name_fused", pd.Series([None] * len(result), index=result.index))
    elif domain == "roads":
        if "fclass" not in result.columns:
            result["fclass"] = result.get("road_class", pd.Series([None] * len(result), index=result.index))
        if "FID_1" not in result.columns and "id" in result.columns:
            result["FID_1"] = result["id"]
    elif domain == "waterways":
        if "waterway_class" not in result.columns:
            result["waterway_class"] = result.get("fclass", pd.Series([None] * len(result), index=result.index))
        if "supplement_source" not in result.columns:
            result["supplement_source"] = result.get("source_name", pd.Series([None] * len(result), index=result.index))
    elif domain == "lakes":
        if "osm_lake_id" not in result.columns:
            result["osm_lake_id"] = result.get("osm_id", pd.Series([None] * len(result), index=result.index))
        if "osm_area_m2" not in result.columns and not result.empty:
            area_frame = result.to_crs("EPSG:3857") if result.crs else result
            result["osm_area_m2"] = area_frame.geometry.area.values
    elif domain == "poi":
        if "id" not in result.columns:
            result["id"] = result.get("source_feature_id", pd.Series([None] * len(result), index=result.index))
        if "source" not in result.columns:
            result["source"] = result.get("source_name", pd.Series([None] * len(result), index=result.index))
        if "sourceid" not in result.columns:
            result["sourceid"] = result.get("source_feature_id", pd.Series([None] * len(result), index=result.index))
        if "type" not in result.columns:
            result["type"] = result.get("fclass", pd.Series([None] * len(result), index=result.index))
        if "lat" not in result.columns and not result.empty:
            points = result.to_crs(OUTPUT_CRS).geometry.apply(lambda geom: geom.representative_point())
            result["lat"] = points.y
            result["lon"] = points.x

    for field in fields:
        if field not in result.columns:
            result[field] = None
    return result[[*fields, result.geometry.name]]


def _drop_empty_name_poi(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if "name" not in frame.columns or frame.empty:
        return frame.copy()
    values = frame["name"].fillna("").astype(str).str.strip()
    return frame[values.ne("")].copy().reset_index(drop=True)


def _backfill_building_height(
    buildings: gpd.GeoDataFrame,
    reference_3d: gpd.GeoDataFrame,
    *,
    min_overlap_ratio: float = 0.05,
    max_nearest_m: float = 8.0,
) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    result = buildings.copy()
    if result.empty:
        return result, {"filled_height": 0, "remaining_missing_height": 0}
    if "Height" not in result.columns:
        result["Height"] = None
    if "H_Raster" not in result.columns:
        result["H_Raster"] = None
    valid_ref = reference_3d[reference_3d.get("Height", pd.Series(dtype=float)).map(_valid_height)].copy()
    if valid_ref.empty:
        missing = int((~result["Height"].map(_valid_height)).sum())
        return result, {"filled_height": 0, "median_fallback_height": 0, "remaining_missing_height": missing}
    if result.crs != valid_ref.crs:
        valid_ref = valid_ref.to_crs(result.crs)
    sindex = valid_ref.sindex
    filled = 0
    median_fallback = 0
    fallback_height = float(valid_ref["Height"].astype(float).median())
    for idx, row in result.iterrows():
        if _valid_height(row.get("Height")):
            continue
        geom = row.geometry
        best_height: float | None = None
        best_score = 0.0
        area = max(float(geom.area), 1e-9)
        for ref_pos in sindex.intersection(geom.bounds):
            ref_row = valid_ref.iloc[int(ref_pos)]
            if not geom.intersects(ref_row.geometry):
                continue
            inter = float(geom.intersection(ref_row.geometry).area)
            score = inter / area
            if score >= min_overlap_ratio and score > best_score:
                best_score = score
                best_height = _as_numeric(ref_row["Height"])
        if best_height is None:
            indices, distances = valid_ref.sindex.nearest(geom, return_distance=True)
            if len(indices) > 0 and len(distances) > 0:
                ref_pos = int(indices[1][0] if getattr(indices, "ndim", 1) == 2 else indices[0])
                if float(distances[0]) <= max_nearest_m:
                    best_height = _as_numeric(valid_ref.iloc[ref_pos]["Height"])
        if best_height is not None:
            result.at[idx, "Height"] = best_height
            result.at[idx, "H_Raster"] = best_height
            filled += 1
    for idx, row in result.iterrows():
        if _valid_height(row.get("Height")):
            continue
        result.at[idx, "Height"] = fallback_height
        result.at[idx, "H_Raster"] = fallback_height
        median_fallback += 1
    missing = int((~result["Height"].map(_valid_height)).sum())
    return result, {
        "filled_height": filled,
        "median_fallback_height": median_fallback,
        "remaining_missing_height": missing,
    }


def _overlap_pairs(frame: gpd.GeoDataFrame, min_area_m2: float = 0.2) -> list[tuple[int, int, float]]:
    if frame.empty:
        return []
    sindex = frame.sindex
    pairs: list[tuple[int, int, float]] = []
    for left_pos, (_, left) in enumerate(frame.iterrows()):
        for right_pos in sindex.intersection(left.geometry.bounds):
            right_pos = int(right_pos)
            if right_pos <= left_pos:
                continue
            right = frame.iloc[right_pos]
            if not left.geometry.intersects(right.geometry):
                continue
            area = float(left.geometry.intersection(right.geometry).area)
            if area >= min_area_m2:
                pairs.append((left_pos, right_pos, area))
    return pairs


def _mitigate_building_overlaps(
    buildings: gpd.GeoDataFrame,
    *,
    delete_cover_ratio: float = 0.65,
    max_shift_m: float = 3.0,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    if buildings.empty:
        return buildings.copy(), {"deleted_small_overlaps": 0, "shifted_buildings": 0, "remaining_overlap_pairs": 0}
    result = buildings.copy().reset_index(drop=True)
    pairs = _overlap_pairs(result)
    delete_indices: set[int] = set()
    for left_pos, right_pos, overlap_area in pairs:
        left_area = float(result.iloc[left_pos].geometry.area)
        right_area = float(result.iloc[right_pos].geometry.area)
        if left_area <= right_area:
            small_pos, small_area = left_pos, left_area
        else:
            small_pos, small_area = right_pos, right_area
        if small_area > 0 and overlap_area / small_area >= delete_cover_ratio:
            delete_indices.add(small_pos)
    if delete_indices:
        result = result.drop(index=sorted(delete_indices)).reset_index(drop=True)

    shifted: set[int] = set()
    for iteration in range(6):
        pairs = _overlap_pairs(result)
        if not pairs:
            break
        for left_pos, right_pos, _overlap_area in pairs:
            if left_pos in shifted and right_pos in shifted:
                continue
            left = result.iloc[left_pos].geometry
            right = result.iloc[right_pos].geometry
            move_pos = left_pos if left.area <= right.area else right_pos
            other = right if move_pos == left_pos else left
            geom = result.iloc[move_pos].geometry
            dx = geom.centroid.x - other.centroid.x
            dy = geom.centroid.y - other.centroid.y
            if dx == 0 and dy == 0:
                dx = max_shift_m
            norm = (dx * dx + dy * dy) ** 0.5
            step = max_shift_m * (iteration + 1)
            result.at[move_pos, result.geometry.name] = affinity.translate(
                geom,
                xoff=step * dx / norm,
                yoff=step * dy / norm,
            )
            if "opt_dx" in result.columns:
                result.at[move_pos, "opt_dx"] = (result.at[move_pos, "opt_dx"] or 0) + step * dx / norm
            if "opt_dy" in result.columns:
                result.at[move_pos, "opt_dy"] = (result.at[move_pos, "opt_dy"] or 0) + step * dy / norm
            shifted.add(move_pos)
    pairs = _overlap_pairs(result)
    extra_delete_indices: set[int] = set()
    for left_pos, right_pos, _overlap_area in pairs:
        left_area = float(result.iloc[left_pos].geometry.area)
        right_area = float(result.iloc[right_pos].geometry.area)
        extra_delete_indices.add(left_pos if left_area <= right_area else right_pos)
    if extra_delete_indices:
        result = result.drop(index=sorted(extra_delete_indices)).reset_index(drop=True)
    remaining = len(_overlap_pairs(result))
    return result, {
        "deleted_small_overlaps": len(delete_indices) + len(extra_delete_indices),
        "shifted_buildings": len(shifted),
        "remaining_overlap_pairs": remaining,
    }


def _read_layer(path: Path, layer: str) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path, layer=layer, engine="pyogrio")
    if frame.crs is None:
        frame = frame.set_crs(OUTPUT_CRS)
    return frame


def _write_gpkg(path: Path, layer: str, frame: gpd.GeoDataFrame) -> None:
    if path.exists():
        path.unlink()
    frame.to_crs(OUTPUT_CRS).to_file(path, layer=layer, driver="GPKG")


def _write_shp(output_dir: Path, name: str, frame: gpd.GeoDataFrame) -> Path | None:
    if frame.empty:
        return None
    path = output_dir / f"{name}.shp"
    frame = frame.to_crs(OUTPUT_CRS)
    frame.to_file(path, driver="ESRI Shapefile", encoding="UTF-8")
    return path


def run_country(config: CountryPostprocessConfig, *, overwrite: bool = True) -> dict[str, Any]:
    shp_dir = config.fusion_dir / "shp"
    if shp_dir.exists() and overwrite:
        shutil.rmtree(shp_dir)
    shp_dir.mkdir(parents=True, exist_ok=not overwrite)
    intermediate_dir = shp_dir / "intermediate"
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    buildings = _read_layer(config.fusion_dir / "fused_buildings.gpkg", "fused_buildings").to_crs(config.target_crs)
    roads = _read_layer(config.fusion_dir / "fused_roads.gpkg", "fused_roads")
    lakes = _read_layer(config.fusion_dir / "fused_water.gpkg", "fused_water_polygons")
    waterways = _read_layer(config.fusion_dir / "fused_water.gpkg", "fused_water_lines")
    poi = _read_layer(config.fusion_dir / "fused_poi.gpkg", "fused_poi")
    ref_3d = _read_layer(config.clip_gpkg, "3d_globfp_buildings").to_crs(config.target_crs)

    buildings = _standardize_columns(buildings, "buildings")
    buildings, height_stats = _backfill_building_height(buildings, ref_3d)
    before_overlap_pairs = len(_overlap_pairs(buildings))
    buildings, overlap_stats = _mitigate_building_overlaps(buildings)
    buildings = _standardize_columns(buildings, "buildings")

    roads = _standardize_columns(roads, "roads")
    lakes = _standardize_columns(lakes, "lakes")
    waterways = _standardize_columns(waterways, "waterways")
    poi_input_count = len(poi)
    poi = _drop_empty_name_poi(_standardize_columns(poi, "poi"))

    outputs = {
        "buildings": buildings,
        "roads": roads,
        "lakes": lakes,
        "waterways": waterways,
        "poi": poi,
    }
    gpkg_path = intermediate_dir / "cleaned_standardized.gpkg"
    if gpkg_path.exists():
        gpkg_path.unlink()
    for layer, frame in outputs.items():
        frame.to_crs(OUTPUT_CRS).to_file(gpkg_path, layer=layer, driver="GPKG")
    shp_paths = {layer: _write_shp(shp_dir, layer, frame) for layer, frame in outputs.items()}

    summary = {
        "country": config.label,
        "target_crs": config.target_crs,
        "standard_reference": r"E:\fyx\data\巴基斯坦\培训文件夹\*_clip.gpkg",
        "counts": {layer: len(frame) for layer, frame in outputs.items()},
        "height_stats": height_stats,
        "poi_removed_empty_name": poi_input_count - len(poi),
        "overlap_stats": {"before_overlap_pairs": before_overlap_pairs, **overlap_stats},
        "shp_outputs": {key: value for key, value in shp_paths.items() if value is not None},
        "intermediate_gpkg": gpkg_path,
    }
    (shp_dir / "postprocess_summary.json").write_text(
        json.dumps(_json_safe(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "country": config.label,
                "layer": layer,
                "feature_count": len(frame),
                "shp_output": str(shp_paths[layer]) if shp_paths[layer] else "",
            }
            for layer, frame in outputs.items()
        ]
    ).to_csv(shp_dir / "postprocess_summary.csv", index=False, encoding="utf-8-sig")
    return summary
