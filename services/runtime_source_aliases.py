from __future__ import annotations

from pathlib import Path


BUILDING_SOURCE_ALIASES: dict[str, str] = {
    "raw.microsoft.building": "MS",
    "raw.local.microsoft.building": "MICROSOFT_LOCAL",
    "raw.openbuildingmap.building": "OBM",
    "raw.google.open_buildings.vector": "GOOGLE_OPEN_BUILDINGS",
    "raw.google.building": "GOOGLE",
    "raw.osm.building": "OSM",
}

BUILDING_SOURCE_PRIORITY_ORDER: tuple[str, ...] = (
    "MS",
    "MICROSOFT_LOCAL",
    "OBM",
    "GOOGLE_OPEN_BUILDINGS",
    "GOOGLE",
    "OSM",
)

BUILDING_HEIGHT_RASTER_PRIORITY_ORDER: tuple[str, ...] = (
    "raw.google.open_buildings_2_5d.height_raster",
    "raw.3d_globfp.building_height.raster",
    "raw.google.building_height.raster",
    "raw.local.building_height.raster",
)

POI_SOURCE_ALIASES: dict[str, str] = {
    "raw.osm.poi": "OSM",
    "raw.gns.poi": "GNG",
    "raw.geonames.poi": "GNG",
    "raw.google.poi": "GOOGLE",
    "raw.rh.poi": "RH",
}

POI_SOURCE_PRIORITY_ORDER: tuple[str, ...] = ("GNG", "GOOGLE", "OSM", "RH")

LINE_SOURCE_ALIASES: dict[str, str] = {
    "raw.osm.road": "OSM",
    "raw.microsoft.road": "MS",
    "raw.overture.transportation": "OVERTURE",
    "raw.overture.road": "OVERTURE",
    "raw.osm.waterways": "OSM",
    "raw.hydrorivers.water": "HYDRORIVERS",
    "raw.local.pakistan.waterways": "LOCAL_WATERWAYS",
}

POLYGON_WATER_SOURCE_ALIASES: dict[str, str] = {
    "raw.osm.water": "OSM",
    "raw.hydrolakes.water": "HYDROLAKES",
    "raw.local.water": "LOCAL_WATER",
}


def alias_paths(component_paths: dict[str, Path], aliases: dict[str, str]) -> dict[str, Path]:
    aliased_paths: dict[str, Path] = {}
    source_ids_by_alias: dict[str, list[str]] = {}
    for source_id, path in component_paths.items():
        alias = aliases.get(source_id)
        if alias is None:
            continue
        if alias in aliased_paths:
            source_ids = [*source_ids_by_alias[alias], source_id]
            raise ValueError(
                f"Duplicate runtime source alias {alias!r} for source ids: {', '.join(source_ids)}"
            )
        aliased_paths[alias] = path
        source_ids_by_alias[alias] = [source_id]
    return aliased_paths
