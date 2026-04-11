from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import geopandas as gpd
from shapely.geometry import box

from services.input_acquisition_service import BBox, MaterializedInputBundle
from utils.crs import normalize_target_crs
from utils.shp_zip import zip_shapefile_bundle


def _first_shp(directory: Path) -> Path:
    matches = sorted(directory.glob("*.shp"))
    if not matches:
        raise FileNotFoundError(f"No shapefile found in {directory}")
    return matches[0]


@dataclass(frozen=True)
class SourceBundleSpec:
    source_id: str
    osm_path: Path
    ref_path: Optional[Path]


class LocalBundleCatalogProvider:
    def __init__(self, root_dir: Path) -> None:
        root = Path(root_dir)
        self.specs = {
            "catalog.flood.building": SourceBundleSpec(
                source_id="catalog.flood.building",
                osm_path=_first_shp(root / "Data" / "buildings" / "OSM"),
                ref_path=_first_shp(root / "Data" / "buildings" / "Google"),
            ),
            "catalog.earthquake.building": SourceBundleSpec(
                source_id="catalog.earthquake.building",
                osm_path=_first_shp(root / "Data" / "buildings" / "OSM"),
                ref_path=_first_shp(root / "Data" / "buildings" / "Google"),
            ),
            "catalog.earthquake.road": SourceBundleSpec(
                source_id="catalog.earthquake.road",
                osm_path=_first_shp(root / "Data" / "roads" / "OSM"),
                ref_path=None,
            ),
            "catalog.typhoon.road": SourceBundleSpec(
                source_id="catalog.typhoon.road",
                osm_path=_first_shp(root / "Data" / "roads" / "OSM"),
                ref_path=None,
            ),
        }

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.specs

    def current_version(self, source_id: str) -> str:
        spec = self.specs[source_id]
        timestamps = [spec.osm_path.stat().st_mtime]
        if spec.ref_path is not None and spec.ref_path.exists():
            timestamps.append(spec.ref_path.stat().st_mtime)
        return "|".join(str(int(value)) for value in timestamps)

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        spec = self.specs[source_id]
        target_dir.mkdir(parents=True, exist_ok=True)
        osm_dir = target_dir / "osm"
        ref_dir = target_dir / "ref"
        osm_dir.mkdir(parents=True, exist_ok=True)
        ref_dir.mkdir(parents=True, exist_ok=True)

        osm, request_space_bbox = self._load_frame(spec.osm_path, request_bbox=request_bbox, target_crs=target_crs)
        ref, _ = self._load_frame(spec.ref_path, request_bbox=request_bbox, target_crs=target_crs)
        if ref is None:
            ref = osm.iloc[0:0].copy()

        osm_shp = osm_dir / "osm.shp"
        ref_shp = ref_dir / "ref.shp"
        osm.to_file(osm_shp)
        ref.to_file(ref_shp)

        return MaterializedInputBundle(
            osm_zip_path=zip_shapefile_bundle(osm_shp, target_dir / "osm.zip"),
            ref_zip_path=zip_shapefile_bundle(ref_shp, target_dir / "ref.zip"),
            bbox=request_space_bbox,
            target_crs=normalize_target_crs(target_crs),
        )

    @staticmethod
    def _load_frame(
        path: Optional[Path],
        *,
        request_bbox: Optional[BBox],
        target_crs: str,
    ) -> tuple[Optional[gpd.GeoDataFrame], Optional[BBox]]:
        if path is None or not path.exists():
            return None, None
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        if request_bbox is not None:
            gdf = gdf.clip(box(*request_bbox))
            gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
        request_space_bbox = LocalBundleCatalogProvider._frame_bbox(gdf)
        target = normalize_target_crs(target_crs)
        gdf = gdf.to_crs(target)
        return gdf, request_space_bbox

    @staticmethod
    def _frame_bbox(gdf: gpd.GeoDataFrame) -> Optional[BBox]:
        if gdf.empty:
            return None
        minx, miny, maxx, maxy = [float(value) for value in gdf.total_bounds.tolist()]
        return (minx, miny, maxx, maxy)
