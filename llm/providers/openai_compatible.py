from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlsplit

from kg.knowledge_release import semantic_hash
from llm.providers.base import LLMProvider


def _extract_json_block(text: str, *, allow_salvage: bool = True) -> tuple[Dict[str, Any], str]:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text), "strict_json"

    if not allow_salvage:
        raise ValueError("LLM output is not a strict JSON object.")

    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("LLM output does not contain a JSON object.")
    return json.loads(match.group(0)), "regex_salvage"


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_sec: int = 60,
        allow_json_salvage: bool = True,
        max_output_tokens: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.allow_json_salvage = allow_json_salvage
        self.max_output_tokens = max_output_tokens

    def probe_connection(self) -> None:
        parsed_url = urlsplit(self.base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise RuntimeError("LLM connection probe failed: base_url must be an HTTP(S) URL.")

        request = urllib.request.Request(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                status = int(getattr(response, "status", 200))
                if status < 200 or status >= 300:
                    raise RuntimeError(f"LLM connection probe failed: HTTP {status}.")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"LLM connection probe failed: HTTP {exc.code}.") from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"LLM connection probe timed out after {self.timeout_sec} seconds."
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise RuntimeError(
                    f"LLM connection probe timed out after {self.timeout_sec} seconds."
                ) from exc
            raise RuntimeError("LLM connection probe failed: endpoint is unreachable.") from exc
        except OSError as exc:
            raise RuntimeError("LLM connection probe failed: endpoint is unreachable.") from exc

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
        self.last_usage = None
        self.last_model = self.model
        self.last_attempt = None
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
        if self.max_output_tokens is not None:
            payload["max_tokens"] = self.max_output_tokens

        data = json.dumps(payload).encode("utf-8")
        started_at = datetime.now(timezone.utc).isoformat()
        started_perf = time.perf_counter()
        attempt: Dict[str, Any] = {
            "provider": self.provider_name,
            "requested_model": self.model,
            "response_model": None,
            "base_url_host": urlsplit(self.base_url).netloc,
            "started_at": started_at,
            "finished_at": None,
            "latency_ms": None,
            "prompt_hash": semantic_hash(system_prompt),
            "context_hash": semantic_hash(context),
            "request_hash": semantic_hash(payload),
            "http_status": None,
            "request_id": None,
            "finish_reason": None,
            "usage": None,
            "raw_response": None,
            "parse_mode": None,
            "transport_retry_count": 0,
            "success": False,
            "failure_class": None,
            "error": None,
        }
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
                attempt["http_status"] = int(getattr(resp, "status", 200))
                headers = getattr(resp, "headers", None)
                if headers is not None:
                    attempt["request_id"] = headers.get("x-request-id") or headers.get("request-id")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            attempt.update(http_status=exc.code, raw_response=detail, failure_class="http_error", error=str(exc))
            self._finish_attempt(attempt, started_perf)
            raise RuntimeError(f"LLM request failed: HTTP {exc.code} {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            attempt.update(failure_class="transport_error", error=str(exc))
            self._finish_attempt(attempt, started_perf)
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        attempt["raw_response"] = body
        try:
            payload_resp = json.loads(body)
            self.last_usage = payload_resp.get("usage")
            self.last_model = str(payload_resp.get("model") or self.model)
            choice = payload_resp["choices"][0]
            content = choice["message"]["content"]
            plan, parse_mode = _extract_json_block(content, allow_salvage=self.allow_json_salvage)
            attempt.update(
                response_model=self.last_model,
                request_id=attempt["request_id"] or payload_resp.get("id"),
                finish_reason=choice.get("finish_reason"),
                usage=self.last_usage,
                parse_mode=parse_mode,
                success=True,
            )
            return plan
        except Exception as exc:  # noqa: BLE001
            attempt.update(failure_class="semantic_parse_error", error=str(exc))
            raise
        finally:
            self._finish_attempt(attempt, started_perf)

    def _finish_attempt(self, attempt: Dict[str, Any], started_perf: float) -> None:
        attempt["finished_at"] = datetime.now(timezone.utc).isoformat()
        attempt["latency_ms"] = max(0, round((time.perf_counter() - started_perf) * 1000))
        self.last_attempt = dict(attempt)
