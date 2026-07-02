from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from services.aoi_resolution_service import AOIAmbiguityError, AOIResolutionService, AdminBoundaryResolver


class FakeGeocoder:
    def __init__(self, results):
        self.results = results
        self.queries: list[str] = []

    def search(self, query: str):
        self.queries.append(query)
        return list(self.results)


class QueryMappedGeocoder:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query
        self.queries: list[str] = []

    def search(self, query: str):
        self.queries.append(query)
        return list(self.results_by_query.get(query, []))


def test_aoi_resolution_service_selects_nairobi_when_query_mentions_kenya() -> None:
    service = AOIResolutionService(
        geocoder=FakeGeocoder(
            [
                {
                    "display_name": "Nairobi, Nairobi County, Kenya",
                    "lat": "-1.286389",
                    "lon": "36.817223",
                    "boundingbox": ["-1.45", "-1.10", "36.65", "37.10"],
                    "class": "boundary",
                    "type": "administrative",
                    "importance": 0.97,
                    "address": {
                        "city": "Nairobi",
                        "state": "Nairobi County",
                        "country": "Kenya",
                        "country_code": "ke",
                    },
                }
            ]
        )
    )

    resolved = service.resolve("fuse building and road data for Nairobi, Kenya")

    assert resolved.display_name == "Nairobi, Nairobi County, Kenya"
    assert resolved.country_code == "ke"
    assert resolved.bbox == (36.65, -1.45, 37.10, -1.10)


def test_aoi_resolution_service_supports_deterministic_fake_geocoder_maturity_path() -> None:
    geocoder = FakeGeocoder(
        [
            {
                "display_name": "Nairobi, Kenya",
                "boundingbox": ["-1.45", "-1.15", "36.65", "37.05"],
                "address": {"country": "Kenya", "country_code": "ke", "city": "Nairobi"},
                "importance": 0.91,
            }
        ]
    )
    service = AOIResolutionService(geocoder=geocoder)

    resolved = service.resolve("need building data for Nairobi, Kenya")

    assert geocoder.queries == ["Nairobi, Kenya"]
    assert resolved.display_name == "Nairobi, Kenya"
    assert resolved.country_name == "Kenya"
    assert resolved.country_code == "ke"
    assert resolved.bbox == (36.65, -1.45, 37.05, -1.15)
    assert resolved.selection_reason == "single_candidate"
    assert resolved.confidence == pytest.approx(0.91)


def test_admin_boundary_required_for_disaster_aoi() -> None:
    geocoder = FakeGeocoder(
        [
            {
                "display_name": "Abidjan, Abidjan Autonomous District, Cote d'Ivoire",
                "boundingbox": ["5.20", "5.50", "-4.15", "-3.85"],
                "address": {"city": "Abidjan", "country": "Cote d'Ivoire", "country_code": "ci"},
                "importance": 0.94,
                "type": "administrative",
            }
        ]
    )
    service = AOIResolutionService(geocoder=geocoder)

    resolved = service.resolve("科特迪瓦阿比让强降雨致12死5伤，请执行灾害地理空间数据融合。")

    assert geocoder.queries == ["Abidjan, Cote d'Ivoire"]
    assert resolved.display_name == "Abidjan, Abidjan Autonomous District, Cote d'Ivoire"
    assert resolved.admin_level == "city"
    assert resolved.boundary_source_id == "bbox_fallback"
    assert resolved.boundary_artifact_path is None
    assert resolved.clip_geometry_hash
    assert resolved.degraded_bbox_clip is True
    payload = resolved.to_dict()
    assert payload["clip_geometry_hash"] == resolved.clip_geometry_hash
    assert payload["degraded_bbox_clip"] is True


def test_aoi_resolution_service_uses_local_admin_boundary_artifact(tmp_path: Path) -> None:
    boundary_path = tmp_path / "Data" / "admin" / "OSM" / "abidjan_boundary.gpkg"
    boundary_path.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"name": ["Abidjan"]},
        geometry=[
            Polygon(
                [
                    (-4.15, 5.20),
                    (-4.15, 5.50),
                    (-4.00, 5.50),
                    (-4.00, 5.35),
                    (-3.85, 5.35),
                    (-3.85, 5.20),
                    (-4.15, 5.20),
                ]
            )
        ],
        crs="EPSG:4326",
    ).to_file(boundary_path, driver="GPKG")
    geocoder = FakeGeocoder(
        [
            {
                "display_name": "Abidjan, Abidjan Autonomous District, Cote d'Ivoire",
                "boundingbox": ["5.20", "5.50", "-4.15", "-3.85"],
                "address": {"city": "Abidjan", "country": "Cote d'Ivoire", "country_code": "ci"},
                "importance": 0.94,
                "type": "administrative",
            }
        ]
    )
    service = AOIResolutionService(
        geocoder=geocoder,
        admin_boundary_resolver=AdminBoundaryResolver(
            repo_root=tmp_path,
            cache_dir=tmp_path / "cache",
        ),
    )

    resolved = service.resolve("flood in Abidjan, Cote d'Ivoire")

    assert resolved.boundary_source_id == "raw.osm.admin_boundary"
    assert resolved.boundary_artifact_path is not None
    assert Path(resolved.boundary_artifact_path).exists()
    assert resolved.clip_geometry_hash
    assert resolved.degraded_bbox_clip is False


def test_aoi_resolution_service_rejects_ambiguous_place_names() -> None:
    service = AOIResolutionService(
        geocoder=FakeGeocoder(
            [
                {
                    "display_name": "Springfield, Illinois, United States",
                    "lat": "39.799",
                    "lon": "-89.644",
                    "boundingbox": ["39.70", "39.89", "-89.74", "-89.55"],
                    "class": "boundary",
                    "type": "administrative",
                    "importance": 0.55,
                    "address": {
                        "city": "Springfield",
                        "state": "Illinois",
                        "country": "United States",
                        "country_code": "us",
                    },
                },
                {
                    "display_name": "Springfield, Massachusetts, United States",
                    "lat": "42.101",
                    "lon": "-72.589",
                    "boundingbox": ["42.05", "42.16", "-72.66", "-72.49"],
                    "class": "boundary",
                    "type": "administrative",
                    "importance": 0.54,
                    "address": {
                        "city": "Springfield",
                        "state": "Massachusetts",
                        "country": "United States",
                        "country_code": "us",
                    },
                },
            ]
        )
    )

    with pytest.raises(AOIAmbiguityError):
        service.resolve("Springfield")


def test_aoi_resolution_service_deduplicates_equivalent_candidates_before_raising_ambiguity() -> None:
    service = AOIResolutionService(
        geocoder=FakeGeocoder(
            [
                {
                    "display_name": "Nairobi, Kenya",
                    "country_code": "ke",
                    "importance": 0.67,
                    "boundingbox": ["-1.4448", "-1.1606", "36.6647", "37.1048"],
                    "address": {"city": "Nairobi", "country": "Kenya", "country_code": "ke"},
                    "type": "administrative",
                },
                {
                    "display_name": "Nairobi, Kenya",
                    "country_code": "ke",
                    "importance": 0.67,
                    "boundingbox": ["-1.4448", "-1.1606", "36.6647", "37.1048"],
                    "address": {"city": "Nairobi", "country": "Kenya", "country_code": "ke"},
                    "type": "city",
                },
            ]
        )
    )

    resolved = service.resolve("fuse building and road data for Nairobi, Kenya")

    assert resolved.display_name == "Nairobi, Kenya"
    assert resolved.country_code == "ke"
    assert resolved.bbox == pytest.approx((36.6647, -1.4448, 37.1048, -1.1606))


def test_aoi_resolution_service_prefers_city_over_broader_admin_candidate_with_same_name() -> None:
    service = AOIResolutionService(
        geocoder=FakeGeocoder(
            [
                {
                    "display_name": "Gitega, Burundi",
                    "boundingbox": ["-3.5884953", "-3.2684953", "29.7649718", "30.0849718"],
                    "importance": 0.5101626528522342,
                    "type": "city",
                    "address": {
                        "city": "Gitega",
                        "state": "Gitega",
                        "country": "Burundi",
                        "country_code": "bi",
                    },
                },
                {
                    "display_name": "Gitega, Burundi",
                    "boundingbox": ["-3.8447564", "-3.0565759", "29.7178599", "30.1040215"],
                    "importance": 0.455650219131522,
                    "type": "administrative",
                    "address": {
                        "state": "Gitega",
                        "country": "Burundi",
                        "country_code": "bi",
                    },
                },
            ]
        )
    )

    resolved = service.resolve("need building data for Gitega, Burundi")

    assert resolved.display_name == "Gitega, Burundi"
    assert resolved.country_code == "bi"
    assert resolved.selection_reason == "nested_specificity_preference"
    assert resolved.bbox == pytest.approx((29.7649718, -3.5884953, 30.0849718, -3.2684953))


def test_aoi_resolution_service_falls_back_past_ambiguous_spanish_admin_alias() -> None:
    geocoder = QueryMappedGeocoder(
        {
            "Cercado de Arequipa, Peru": [
                {
                    "display_name": "Universidad Tecnologica del Peru, Arequipa, Peru",
                    "boundingbox": ["-16.4094", "-16.4085", "-71.5411", "-71.5399"],
                    "importance": 0.38,
                    "type": "university",
                    "address": {"city": "Arequipa", "country": "Peru", "country_code": "pe"},
                },
                {
                    "display_name": "Universidad Tecnologica del Peru, Calle La Merced, Arequipa, Peru",
                    "boundingbox": ["-16.4012", "-16.4007", "-71.5388", "-71.5382"],
                    "importance": 0.38,
                    "type": "university",
                    "address": {"city": "Arequipa", "country": "Peru", "country_code": "pe"},
                },
            ],
            "Arequipa Cercado, Peru": [
                {
                    "display_name": "Arequipa, Arequipa, Peru",
                    "boundingbox": ["-16.43", "-16.37", "-71.57", "-71.50"],
                    "importance": 0.31,
                    "type": "administrative",
                    "address": {
                        "city": "Arequipa",
                        "state": "Arequipa",
                        "country": "Peru",
                        "country_code": "pe",
                    },
                }
            ],
        }
    )
    service = AOIResolutionService(geocoder=geocoder)

    resolved = service.resolve("fuse building data for flood response in Distrito de Arequipa Cercado, Peru")

    assert geocoder.queries == [
        "Distrito de Arequipa Cercado, Peru",
        "Cercado de Arequipa, Peru",
        "Arequipa Cercado, Peru",
    ]
    assert resolved.query == "Distrito de Arequipa Cercado, Peru"
    assert resolved.display_name == "Arequipa, Arequipa, Peru"
    assert resolved.country_code == "pe"


def test_aoi_resolution_service_falls_back_for_portuguese_admin_prefix_when_exact_query_misses() -> None:
    geocoder = QueryMappedGeocoder(
        {
            "Se, Sao Paulo, Brazil": [
                {
                    "display_name": "Se, Sao Paulo, Brazil",
                    "boundingbox": ["-23.56", "-23.53", "-46.65", "-46.62"],
                    "importance": 0.69,
                    "type": "administrative",
                    "address": {
                        "suburb": "Se",
                        "city": "Sao Paulo",
                        "country": "Brazil",
                        "country_code": "br",
                    },
                }
            ],
        }
    )
    service = AOIResolutionService(geocoder=geocoder)

    resolved = service.resolve("fuse poi data for emergency operations around Freguesia de Se, Sao Paulo, Brazil")

    assert geocoder.queries == [
        "Freguesia de Se, Sao Paulo, Brazil",
        "Se, Sao Paulo, Brazil",
    ]
    assert resolved.query == "Freguesia de Se, Sao Paulo, Brazil"
    assert resolved.display_name == "Se, Sao Paulo, Brazil"
    assert resolved.country_code == "br"


def test_extract_location_query_removes_disaster_suffix() -> None:
    assert (
        AOIResolutionService.extract_location_query(
            "fuse building and road data for Parakou, Benin after an earthquake"
        )
        == "Parakou, Benin"
    )


def test_extract_location_query_supports_disaster_prefix() -> None:
    assert (
        AOIResolutionService.extract_location_query(
            "earthquake in Parakou, Benin, need building and road fusion"
        )
        == "Parakou, Benin"
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("fuse building data for conflict response in Gitega, Burundi", "Gitega, Burundi"),
        ("fuse road data for wildfire relief near Valparaiso, Chile", "Valparaiso, Chile"),
        ("fuse poi data for drought recovery within Garissa, Kenya", "Garissa, Kenya"),
        (
            "fuse water data for emergency operations around Tacloban, Philippines",
            "Tacloban, Philippines",
        ),
    ],
)
def test_extract_location_query_removes_humanitarian_response_prefix(query: str, expected: str) -> None:
    assert AOIResolutionService.extract_location_query(query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "fuse building data for flood response in Saddar Town, Karachi, Pakistan",
            "Saddar Town, Karachi, Pakistan",
        ),
        (
            "fuse road data for conflict response in Ward 26, Kathmandu, Nepal",
            "Ward 26, Kathmandu, Nepal",
        ),
        (
            "fuse building data for emergency operations around Barangay 656, Intramuros, Manila, Philippines",
            "Barangay 656, Intramuros, Manila, Philippines",
        ),
        (
            "fuse building data for flood response in Distrito de Arequipa Cercado, Peru",
            "Distrito de Arequipa Cercado, Peru",
        ),
    ],
)
def test_extract_location_query_preserves_administrative_qualifiers(query: str, expected: str) -> None:
    assert AOIResolutionService.extract_location_query(query) == expected


def test_extract_location_query_normalizes_chinese_abidjan_event() -> None:
    query = "科特迪瓦阿比让强降雨致12死5伤，请执行灾害地理空间数据融合。"

    assert AOIResolutionService.extract_location_query(query) == "Abidjan, Cote d'Ivoire"
