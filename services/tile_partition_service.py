from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import geopandas as gpd
from shapely.geometry import box

from utils.crs import normalize_target_crs
from utils.vector_clip import BBox, REQUEST_BBOX_CRS


@dataclass(frozen=True)
class TileSpec:
    tile_id: str
    bbox: BBox
    buffered_bbox: BBox
    working_bbox: BBox
    working_buffered_bbox: BBox
    row: int
    col: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TileManifest:
    bbox: BBox
    bbox_crs: str
    working_crs: str
    tile_width_m: float
    tile_height_m: float
    overlap_m: float
    tiles: list[TileSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tiles"] = [tile.to_dict() for tile in self.tiles]
        return payload


class TilePartitionService:
    def __init__(
        self,
        *,
        tile_width_m: float = 5000.0,
        tile_height_m: float = 5000.0,
        overlap_m: float = 64.0,
    ) -> None:
        self.tile_width_m = float(tile_width_m)
        self.tile_height_m = float(tile_height_m)
        self.overlap_m = float(overlap_m)
        if self.tile_width_m <= 0 or self.tile_height_m <= 0:
            raise ValueError("tile_width_m and tile_height_m must be positive")
        if self.overlap_m < 0:
            raise ValueError("overlap_m must be >= 0")

    def partition_bbox(
        self,
        *,
        bbox: BBox,
        bbox_crs: str = REQUEST_BBOX_CRS,
        working_crs: str,
    ) -> TileManifest:
        bbox_crs = normalize_target_crs(bbox_crs)
        working_crs = normalize_target_crs(working_crs)
        working_bounds = self._transform_bounds(bbox, from_crs=bbox_crs, to_crs=working_crs)
        minx, miny, maxx, maxy = working_bounds
        width = max(0.0, maxx - minx)
        height = max(0.0, maxy - miny)
        cols = max(1, int(math.ceil(width / self.tile_width_m)) if width else 1)
        rows = max(1, int(math.ceil(height / self.tile_height_m)) if height else 1)

        tiles: list[TileSpec] = []
        for row in range(rows):
            for col in range(cols):
                tile_minx = minx + col * self.tile_width_m
                tile_maxx = min(maxx, tile_minx + self.tile_width_m)
                tile_miny = miny + row * self.tile_height_m
                tile_maxy = min(maxy, tile_miny + self.tile_height_m)
                working_bbox = (
                    float(tile_minx),
                    float(tile_miny),
                    float(tile_maxx),
                    float(tile_maxy),
                )
                working_buffered_bbox = (
                    float(max(minx, tile_minx - self.overlap_m)),
                    float(max(miny, tile_miny - self.overlap_m)),
                    float(min(maxx, tile_maxx + self.overlap_m)),
                    float(min(maxy, tile_maxy + self.overlap_m)),
                )
                tiles.append(
                    TileSpec(
                        tile_id=f"tile_{row:03d}_{col:03d}",
                        bbox=self._transform_bounds(working_bbox, from_crs=working_crs, to_crs=bbox_crs),
                        buffered_bbox=self._transform_bounds(
                            working_buffered_bbox,
                            from_crs=working_crs,
                            to_crs=bbox_crs,
                        ),
                        working_bbox=working_bbox,
                        working_buffered_bbox=working_buffered_bbox,
                        row=row,
                        col=col,
                    )
                )

        return TileManifest(
            bbox=tuple(float(value) for value in bbox),
            bbox_crs=bbox_crs,
            working_crs=working_crs,
            tile_width_m=self.tile_width_m,
            tile_height_m=self.tile_height_m,
            overlap_m=self.overlap_m,
            tiles=tiles,
        )

    @staticmethod
    def _transform_bounds(bounds: BBox, *, from_crs: str, to_crs: str) -> BBox:
        frame = gpd.GeoSeries([box(*bounds)], crs=from_crs)
        transformed = frame.to_crs(to_crs)
        minx, miny, maxx, maxy = transformed.total_bounds.tolist()
        return (float(minx), float(miny), float(maxx), float(maxy))
