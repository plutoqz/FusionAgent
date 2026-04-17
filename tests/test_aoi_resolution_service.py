from __future__ import annotations

import pytest

from services.aoi_resolution_service import AOIAmbiguityError, AOIResolutionService


class StubGeocoder:
    def __init__(self, results):
        self.results = results
        self.queries: list[str] = []

    def search(self, query: str):
        self.queries.append(query)
        return list(self.results)


def test_aoi_resolution_service_selects_nairobi_when_query_mentions_kenya() -> None:
    service = AOIResolutionService(
        geocoder=StubGeocoder(
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


def test_aoi_resolution_service_rejects_ambiguous_place_names() -> None:
    service = AOIResolutionService(
        geocoder=StubGeocoder(
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
