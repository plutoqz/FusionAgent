from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class LLMProvider(ABC):
    @property
    def provider_name(self) -> str:
        raw = self.__class__.__name__.replace("Provider", "")
        parts = []
        current = []
        for char in raw:
            if char.isupper() and current:
                parts.append("".join(current).lower())
                current = [char]
            else:
                current.append(char)
        if current:
            parts.append("".join(current).lower())
        return "_".join(parts)

    @abstractmethod
    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
