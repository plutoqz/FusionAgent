from __future__ import annotations

from typing import Any


_OFF_DOMAIN_KEYWORDS = (
    "gdp",
    "gross domestic product",
    "国内生产总值",
    "人口",
)

_OUTPUT_SCHEMA_CUSTOMIZATION_KEYWORDS = (
    "中文列名",
    "列名改成中文",
    "属性表列名",
    "rename columns",
)


def _job_type_value(job_type: Any) -> str:
    return str(getattr(job_type, "value", job_type))


def _first_keyword_match(normalized_content: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if keyword.casefold() in normalized_content:
            return keyword
    return None


def classify_unsupported_intent(content: str, *, job_type: str) -> list[dict[str, str]]:
    normalized_content = (content or "").casefold()
    normalized_job_type = _job_type_value(job_type)
    issues: list[dict[str, str]] = []

    off_domain_keyword = _first_keyword_match(normalized_content, _OFF_DOMAIN_KEYWORDS)
    if off_domain_keyword is not None:
        issues.append(
            {
                "code": "OFF_DOMAIN_REQUEST",
                "message": "Request includes off-domain content that the fusion workflow does not support.",
                "matched_keyword": off_domain_keyword.casefold(),
                "job_type": normalized_job_type,
            }
        )

    schema_keyword = _first_keyword_match(normalized_content, _OUTPUT_SCHEMA_CUSTOMIZATION_KEYWORDS)
    if schema_keyword is not None:
        issues.append(
            {
                "code": "UNSUPPORTED_OUTPUT_SCHEMA_CUSTOMIZATION",
                "message": "Request asks for output schema customization that is not supported.",
                "matched_keyword": schema_keyword,
                "job_type": normalized_job_type,
            }
        )

    return issues
