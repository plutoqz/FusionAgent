from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import geopandas as gpd

from kg.source_catalog import CATALOG_BUNDLE_SPECS, CatalogBundleSpec
from services.input_acquisition_service import BBox, MaterializedInputBundle
from services.raw_vector_source_service import MaterializedRawVectorSource, RawVectorSourceService
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


class LocalBundleCatalogProvider:
    def __init__(self, root_dir: Path, *, raw_source_service: RawVectorSourceService) -> None:
        self.root_dir = Path(root_dir)
        self.raw_source_service = raw_source_service
        self.specs = {bundle_spec.source_id: bundle_spec for bundle_spec in CATALOG_BUNDLE_SPECS}

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.specs

    def current_version(self, source_id: str) -> str:
        spec = self._spec_for(source_id)
        tokens = [self.raw_source_service.current_version(spec.osm_source_id)]
        if spec.ref_source_id is not None:
            tokens.append(self.raw_source_service.current_version(spec.ref_source_id))
        return "|".join(tokens)

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        spec = self._spec_for(source_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        osm = self.raw_source_service.resolve(
            source_id=spec.osm_source_id,
            request_bbox=request_bbox,
            target_path=target_dir / "osm.zip",
            target_crs=target_crs,
        )
        if spec.ref_source_id is not None:
            ref = self.raw_source_service.resolve(
                source_id=spec.ref_source_id,
                request_bbox=request_bbox,
                target_path=target_dir / "ref.zip",
                target_crs=target_crs,
            )
        else:
            ref = self._create_empty_reference_bundle(osm=osm, output_zip=target_dir / "ref.zip")

        return MaterializedInputBundle(
            osm_zip_path=osm.zip_path,
            ref_zip_path=ref.zip_path,
            bbox=osm.bbox or ref.bbox,
            target_crs=normalize_target_crs(target_crs),
        )

    def _spec_for(self, source_id: str) -> CatalogBundleSpec:
        return self.specs[source_id]

    @staticmethod
    def _create_empty_reference_bundle(
        *,
        osm: MaterializedRawVectorSource,
        output_zip: Path,
    ) -> MaterializedRawVectorSource:
        extract_dir = output_zip.parent / f"_empty_ref_src_{uuid.uuid4().hex[:8]}"
        shp_path = validate_zip_has_shapefile(osm.zip_path, extract_dir)
        frame = gpd.read_file(shp_path)
        empty = frame.iloc[0:0].copy()

        out_dir = output_zip.parent / f"_empty_ref_dst_{uuid.uuid4().hex[:8]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_shp = out_dir / "ref.shp"
        empty.to_file(ref_shp)
        zip_shapefile_bundle(ref_shp, output_zip)

        return MaterializedRawVectorSource(
            zip_path=output_zip,
            bbox=osm.bbox,
            target_crs=osm.target_crs,
            source_id=f"{osm.source_id}.empty_ref",
            source_mode="generated_empty_ref",
            cache_hit=False,
            version_token=osm.version_token,
        )
