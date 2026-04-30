from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from adapters import fusioncode_building_adapter
from agent.executor import ExecutionContext
from schemas.fusion import JobType


def _write_source(path: Path, height: float) -> None:
    frame = gpd.GeoDataFrame(
        {"height": [height]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:3857",
    )
    frame.to_file(path, driver="GPKG")


def test_multisource_building_adapter_writes_source_and_final_heights(tmp_path: Path, monkeypatch) -> None:
    ms_path = tmp_path / "ms.gpkg"
    obm_path = tmp_path / "obm.gpkg"
    _write_source(ms_path, 4.0)
    _write_source(obm_path, 9.0)

    def fake_fusion(source_map, roads, params, source_priority_order):
        del roads, params, source_priority_order
        assert set(source_map) == {"MS", "OBM"}
        return gpd.GeoDataFrame(
            {"height_fused": [4.0]},
            geometry=[box(0, 0, 1, 1)],
            crs="EPSG:3857",
        )

    monkeypatch.setattr(fusioncode_building_adapter, "run_cascaded_multi_source_fusion", fake_fusion)
    context = ExecutionContext(
        run_id="run-height-adapter",
        job_type=JobType.building,
        osm_shp=tmp_path / "missing_osm.shp",
        ref_shp=tmp_path / "missing_ref.shp",
        output_dir=tmp_path / "out",
        target_crs="EPSG:3857",
        named_vectors={"MS": ms_path, "OBM": obm_path},
    )

    output_path = fusioncode_building_adapter.run_building_multi_source_decomposed(context)
    result = gpd.read_file(output_path)

    assert float(result.loc[0, "height_ms"]) == 4.0
    assert float(result.loc[0, "height_obm"]) == 9.0
    assert float(result.loc[0, "height_vector_fused"]) == 9.0
    assert float(result.loc[0, "height_final"]) == 9.0
    assert result.loc[0, "height_final_source"] == "height_obm"
