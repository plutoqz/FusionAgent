from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class KgGraphNode(BaseModel):
    id: str
    kind: str
    label: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class KgGraphEdge(BaseModel):
    source: str
    target: str
    relationship: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class KgGraphResponse(BaseModel):
    nodes: List[KgGraphNode] = Field(default_factory=list)
    edges: List[KgGraphEdge] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
