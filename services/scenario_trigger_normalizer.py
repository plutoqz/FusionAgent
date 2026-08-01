from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry


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
    def __init__(self, policy_registry: KnowledgePolicyRegistry | None = None) -> None:
        self.policy_registry = policy_registry or default_policy_registry()

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

    def _extract_location(self, text: str) -> dict[str, str]:
        matches: list[tuple[str, dict[str, Any]]] = []
        lowered = text.casefold()
        for payload in self.policy_registry.place_records():
            aliases = [payload.get("term"), payload.get("canonical"), *list(payload.get("aliases") or [])]
            for alias in aliases:
                term = str(alias or "").strip()
                if term and term.casefold() in lowered:
                    matches.append((term, payload))
                    break
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

    def _extract_disaster_type(self, text: str) -> str | None:
        return self.policy_registry.disaster_type_in_text(text)

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

    def _extract_rescue_organizations(self, text: str) -> list[str]:
        organizations = []
        for token in self.policy_registry.rescue_organization_terms():
            if token in text:
                organizations.append(token)
        return organizations


def normalize_scenario_trigger_text(
    text: str,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> NormalizedScenarioTrigger:
    return ScenarioTriggerNormalizer(policy_registry).normalize(text)
