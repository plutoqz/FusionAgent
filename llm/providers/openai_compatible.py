from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict

from llm.providers.base import LLMProvider


def _extract_json_block(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("LLM output does not contain a JSON object.")
    return json.loads(match.group(0))


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_sec: int = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec

    @classmethod
    def from_env(cls) -> "OpenAICompatibleProvider":
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEOFUSION_LLM_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY (or GEOFUSION_LLM_API_KEY) is required for openai provider.")
        model = os.getenv("GEOFUSION_LLM_MODEL", "gpt-5.4-mini")
        base_url = os.getenv("GEOFUSION_LLM_BASE_URL", "https://api.openai.com/v1")
        timeout_sec = int(os.getenv("GEOFUSION_LLM_TIMEOUT_SEC", "60"))
        return cls(api_key=api_key, model=model, base_url=base_url, timeout_sec=timeout_sec)

    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM request failed: HTTP {exc.code} {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        payload_resp = json.loads(body)
        content = payload_resp["choices"][0]["message"]["content"]
        return _extract_json_block(content)
