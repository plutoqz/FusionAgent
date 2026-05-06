from services.tile_partition_service import TilePartitionService


def test_partition_service_splits_large_bbox_into_buffered_tiles() -> None:
    service = TilePartitionService(tile_width_m=5000, tile_height_m=5000, overlap_m=64)

    manifest = service.partition_bbox(
        bbox=(2.48, 9.23, 2.77, 9.44),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:32631",
    )

    assert len(manifest.tiles) >= 2
    assert all(tile.tile_id.startswith("tile_") for tile in manifest.tiles)
    assert all(tile.buffered_bbox is not None for tile in manifest.tiles)
    assert manifest.working_crs == "EPSG:32631"


def test_partition_service_emits_stable_tile_ids_for_same_request() -> None:
    service = TilePartitionService(tile_width_m=5000, tile_height_m=5000, overlap_m=64)

    manifest_a = service.partition_bbox(
        bbox=(2.48, 9.23, 2.77, 9.44),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:32631",
    )
    manifest_b = service.partition_bbox(
        bbox=(2.48, 9.23, 2.77, 9.44),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:32631",
    )

    assert [tile.tile_id for tile in manifest_a.tiles] == [tile.tile_id for tile in manifest_b.tiles]
    assert [tile.working_bbox for tile in manifest_a.tiles] == [tile.working_bbox for tile in manifest_b.tiles]
