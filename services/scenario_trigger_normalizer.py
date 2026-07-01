from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


_CHINESE_LOCATION_ALIASES = {
    "科特迪瓦": {
        "canonical": "Cote d'Ivoire",
        "kind": "country",
        "country_code": "ci",
        "aliases": ("象牙海岸",),
    },
    "阿比让": {
        "canonical": "Abidjan",
        "kind": "city",
        "country": "Cote d'Ivoire",
        "country_code": "ci",
        "aliases": (),
    },
    "巴基斯坦": {
        "canonical": "Pakistan",
        "kind": "country",
        "country_code": "pk",
        "aliases": (),
    },
    "卡拉奇": {
        "canonical": "Karachi",
        "kind": "city",
        "country": "Pakistan",
        "country_code": "pk",
        "aliases": ("卡拉奇市",),
    },
}

_DISASTER_ALIASES = (
    ("flood", ("洪涝", "洪水", "内涝", "强降雨", "暴雨", "降雨", "heavy rainfall", "rainstorm")),
    ("earthquake", ("地震",)),
    ("typhoon", ("台风", "飓风", "热带气旋")),
)


@dataclass(frozen=True)
class NormalizedScenarioTrigger:
    original_text: str
    normalized_location: str | None = None
    country: str | None = None
    country_code: str | None = None
    locality: str | None = None
    disaster_type: str | None = None
    casualty_summary: dict[str, int] | None = None
    rescue_organizations: tuple[str, ...] = ()
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rescue_organizations"] = list(self.rescue_organizations)
        return payload


class ScenarioTriggerNormalizer:
    def normalize(self, text: str) -> NormalizedScenarioTrigger:
        original = str(text or "").strip()
        location = self._extract_location(original)
        disaster_type = self._extract_disaster_type(original)
        casualties = self._extract_casualties(original)
        organizations = self._extract_rescue_organizations(original)
        confidence = 0.0
        if location.get("normalized_location"):
            confidence += 0.7
        if disaster_type:
            confidence += 0.2
        if casualties or organizations:
            confidence += 0.1
        return NormalizedScenarioTrigger(
            original_text=original,
            normalized_location=location.get("normalized_location"),
            country=location.get("country"),
            country_code=location.get("country_code"),
            locality=location.get("locality"),
            disaster_type=disaster_type,
            casualty_summary=casualties or None,
            rescue_organizations=tuple(organizations),
            confidence=min(confidence, 1.0),
        )

    @staticmethod
    def _extract_location(text: str) -> dict[str, str]:
        matches: list[tuple[str, dict[str, Any]]] = []
        for primary, payload in _CHINESE_LOCATION_ALIASES.items():
            aliases = (primary, *tuple(payload.get("aliases") or ()))
            if any(alias and alias in text for alias in aliases):
                matches.append((primary, payload))
        lowered = text.casefold()
        english_aliases = {
            "abidjan": _CHINESE_LOCATION_ALIASES["阿比让"],
            "cote d'ivoire": _CHINESE_LOCATION_ALIASES["科特迪瓦"],
            "côte d'ivoire": _CHINESE_LOCATION_ALIASES["科特迪瓦"],
            "ivory coast": _CHINESE_LOCATION_ALIASES["科特迪瓦"],
            "karachi": _CHINESE_LOCATION_ALIASES["卡拉奇"],
            "pakistan": _CHINESE_LOCATION_ALIASES["巴基斯坦"],
        }
        for alias, payload in english_aliases.items():
            if alias in lowered:
                matches.append((alias, payload))
        if not matches:
            return {}

        country = None
        country_code = None
        locality = None
        for _alias, payload in matches:
            if payload.get("kind") == "country":
                country = str(payload["canonical"])
                country_code = str(payload.get("country_code") or "")
            elif payload.get("kind") == "city":
                locality = str(payload["canonical"])
                country = country or str(payload.get("country") or "")
                country_code = country_code or str(payload.get("country_code") or "")

        if locality and country:
            normalized = f"{locality}, {country}"
        else:
            normalized = locality or country
        return {
            "normalized_location": normalized,
            "country": country or "",
            "country_code": country_code or "",
            "locality": locality or "",
        }

    @staticmethod
    def _extract_disaster_type(text: str) -> str | None:
        lowered = text.casefold()
        for disaster_type, aliases in _DISASTER_ALIASES:
            if any(alias.casefold() in lowered for alias in aliases):
                return disaster_type
        for disaster_type in ("flood", "earthquake", "typhoon"):
            if re.search(rf"(?<![a-z0-9_]){disaster_type}(?![a-z0-9_])", lowered):
                return disaster_type
        return None

    @staticmethod
    def _extract_casualties(text: str) -> dict[str, int]:
        summary: dict[str, int] = {}
        patterns = {
            "deaths": r"(?:造成|致)?\s*(\d+)\s*(?:人)?(?:死亡|遇难|死)",
            "injured": r"(\d+)\s*(?:人)?(?:受伤|伤)",
            "missing": r"(\d+)\s*(?:人)?失踪",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                summary[key] = int(match.group(1))
        return summary

    @staticmethod
    def _extract_rescue_organizations(text: str) -> list[str]:
        organizations = []
        for token in ("红十字会", "消防", "应急管理", "救援队", "联合国"):
            if token in text:
                organizations.append(token)
        return organizations


def normalize_scenario_trigger_text(text: str) -> NormalizedScenarioTrigger:
    return ScenarioTriggerNormalizer().normalize(text)
