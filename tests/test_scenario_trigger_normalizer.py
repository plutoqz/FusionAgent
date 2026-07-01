from __future__ import annotations

from services.scenario_trigger_normalizer import normalize_scenario_trigger_text


def test_scenario_trigger_normalizer_extracts_chinese_abidjan_flood_event() -> None:
    normalized = normalize_scenario_trigger_text("科特迪瓦阿比让强降雨致12死5伤，红十字会参与救援。")

    assert normalized.normalized_location == "Abidjan, Cote d'Ivoire"
    assert normalized.country_code == "ci"
    assert normalized.locality == "Abidjan"
    assert normalized.disaster_type == "flood"
    assert normalized.casualty_summary == {"deaths": 12, "injured": 5}
    assert normalized.rescue_organizations == ("红十字会",)
