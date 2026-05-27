from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ArtifactPreviewResponse(BaseModel):
    run_id: str
    shapefile_name: Optional[str] = None
    geojson_path: str
    max_features: int = 0
    preview_feature_count: int = 0
    feature_count: int = 0
    crs: Optional[str] = None
    geometry_types: list[str] = Field(default_factory=list)
    bbox: Optional[list[float]] = None


class ScenarioDocumentEntry(BaseModel):
    filename: str
    path: str
    size_bytes: int
    language: Optional[str] = None


class ScenarioDocumentListResponse(BaseModel):
    scenario_id: str
    documents: list[ScenarioDocumentEntry] = Field(default_factory=list)


class MarkdownDocumentResponse(BaseModel):
    scenario_id: str
    filename: str
    path: str
    content: str
    size_bytes: int
    language: Optional[str] = None


class RunDocumentEntry(BaseModel):
    filename: str
    path: str
    size_bytes: int
    language: Optional[str] = None


class RunDocumentListResponse(BaseModel):
    run_id: str
    documents: list[RunDocumentEntry] = Field(default_factory=list)


class RunMarkdownDocumentResponse(BaseModel):
    run_id: str
    filename: str
    path: str
    content: str
    size_bytes: int
    language: Optional[str] = None
