from __future__ import annotations

from dataclasses import dataclass, field

from schemas.task_kind import TaskKind


@dataclass(frozen=True)
class DomainOutputContract:
    contract_id: str
    task_kind: TaskKind
    required_fields: list[str]
    preserve_if_present: list[str] = field(default_factory=list)
    field_null_rate_thresholds: dict[str, float] = field(default_factory=dict)
    soft_field_null_rate_thresholds: dict[str, float] = field(default_factory=dict)


_CONTRACTS: dict[TaskKind, DomainOutputContract] = {
    TaskKind.road: DomainOutputContract(
        contract_id="contract.road.fused.v1",
        task_kind=TaskKind.road,
        required_fields=[
            "geometry",
            "fusion_source",
            "match_role",
            "road_class",
            "source_layer",
            "name",
            "osm_name",
            "road_name",
        ],
        preserve_if_present=["source_feature_id", "surface", "lanes", "ref"],
        field_null_rate_thresholds={"name": 0.80, "osm_name": 0.90, "road_name": 0.90},
    ),
    TaskKind.building: DomainOutputContract(
        contract_id="contract.building.fused.v1",
        task_kind=TaskKind.building,
        required_fields=["geometry"],
        preserve_if_present=["source_id", "source_feature_id", "name", "height_m", "Height", "H_Raster"],
        field_null_rate_thresholds={"height_m": 0.50, "Height": 0.50, "H_Raster": 0.50},
    ),
    TaskKind.water_polygon: DomainOutputContract(
        contract_id="contract.water_polygon.fused.v1",
        task_kind=TaskKind.water_polygon,
        required_fields=["geometry"],
        preserve_if_present=["source_id", "source_feature_id", "name", "water_class"],
        field_null_rate_thresholds={"name": 0.95},
    ),
    TaskKind.waterways: DomainOutputContract(
        contract_id="contract.waterways.fused.v1",
        task_kind=TaskKind.waterways,
        required_fields=["geometry", "fusion_source", "match_role", "waterway_class", "source_layer"],
        preserve_if_present=["source_feature_id", "name", "name_en", "name_ur", "width", "depth"],
        field_null_rate_thresholds={"name": 0.95},
    ),
    TaskKind.poi: DomainOutputContract(
        contract_id="contract.poi.fused.v1",
        task_kind=TaskKind.poi,
        required_fields=["geometry"],
        preserve_if_present=["source_id", "source_feature_id", "name", "category", "type"],
        field_null_rate_thresholds={"name": 0.20},
    ),
}


def get_domain_output_contract(
    task_kind: TaskKind,
    *,
    source_expected_null_rates: dict[str, float] | None = None,
) -> DomainOutputContract:
    contract = _CONTRACTS[task_kind]
    thresholds = dict(contract.field_null_rate_thresholds)
    thresholds.update(source_expected_null_rates or {})
    return DomainOutputContract(
        contract_id=contract.contract_id,
        task_kind=contract.task_kind,
        required_fields=list(contract.required_fields),
        preserve_if_present=list(contract.preserve_if_present),
        field_null_rate_thresholds=thresholds,
        soft_field_null_rate_thresholds=dict(contract.soft_field_null_rate_thresholds),
    )
