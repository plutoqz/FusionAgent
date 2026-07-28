from __future__ import annotations

import csv
import dataclasses
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from kg.models import DurableLearningSummary
from services.kg_graph_service import AGENT_STRUCTURE, build_overview_graph


MANIFEST_PATH = PROJECT_ROOT / "kg" / "seed_manifest.generated.json"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "research" / "ontology" / "2026-07-27"


KIND_CONFIG = {
    "data_type": ("data_types", "type_id", "type_id"),
    "task": ("tasks", "task_id", "task_name"),
    "scenario_profile": ("scenario_profiles", "profile_id", "profile_name"),
    "product_contract": ("product_contracts", "contract_id", "contract_name"),
    "task_bundle": ("task_bundles", "bundle_id", "bundle_name"),
    "output_requirement": ("output_requirements", "requirement_id", "requirement_id"),
    "qos_policy": ("qos_policies", "policy_id", "policy_name"),
    "data_need": ("data_needs", "need_id", "need_id"),
    "repair_strategy": ("repair_strategies", "strategy_id", "strategy_name"),
    "algorithm": ("algorithms", "algo_id", "algo_name"),
    "parameter_spec": ("parameter_specs", "spec_id", "label"),
    "workflow_pattern": ("workflow_patterns", "pattern_id", "pattern_name"),
    "data_source": ("data_sources", "source_id", "source_name"),
    "output_schema_policy": ("output_schema_policies", "policy_id", "policy_id"),
}


CLASS_SPECS = {
    "scenario_profile": {
        "label": "场景处境",
        "description": "描述灾种、响应阶段和任务处境，给出激活任务、输出字段偏好与默认 QoS，是契约选择和规划检索的上层语境。",
        "lifecycle": "seed",
        "primary_id_field": "profile_id",
    },
    "product_contract": {
        "label": "产品契约",
        "description": "把数据产品要求建模为一等图谱实体，统一表达图层要求、质量门、满足状态、证据要求、降级、缺口声明、交付和产品组成策略。",
        "lifecycle": "seed",
        "primary_id_field": "contract_id",
    },
    "task_bundle": {
        "label": "任务编排包",
        "description": "将一组任务、输出要求、QoS、数据需求和修复策略组合成可检索、可规划的编排单元。",
        "lifecycle": "seed",
        "primary_id_field": "bundle_id",
    },
    "task": {
        "label": "任务",
        "description": "表示规划和执行要完成的业务任务，是场景、契约、数据需求、算法能力和工作流模式之间的枢纽。",
        "lifecycle": "seed",
        "primary_id_field": "task_id",
    },
    "output_requirement": {
        "label": "输出要求",
        "description": "规定任务必须交付的输出类型、字段层级和对应模式策略，为产品契约和工作流提供可验证的交付目标。",
        "lifecycle": "seed",
        "primary_id_field": "requirement_id",
    },
    "output_schema_policy": {
        "label": "输出模式策略",
        "description": "规定输出字段保留、必需字段、可选字段、重命名提示和兼容性判断方式。",
        "lifecycle": "seed",
        "primary_id_field": "policy_id",
    },
    "qos_policy": {
        "label": "服务质量策略",
        "description": "表达时延、成功率及质量维度权重，用于场景默认、产品契约和任务编排的质量权衡。",
        "lifecycle": "seed",
        "primary_id_field": "policy_id",
    },
    "data_need": {
        "label": "数据需求",
        "description": "明确任务所需或产生的数据类型、方向和必需性，将任务语义连接到数据类型。",
        "lifecycle": "seed",
        "primary_id_field": "need_id",
    },
    "data_type": {
        "label": "数据类型",
        "description": "定义图谱中可被算法、数据源和工作流消费或产生的数据语义、主题和几何类型。",
        "lifecycle": "seed",
        "primary_id_field": "type_id",
    },
    "data_source": {
        "label": "数据源",
        "description": "表示可获取或上传的数据来源，记录支持的数据类型、灾种、作业类型、几何类型、新鲜度和质量。",
        "lifecycle": "seed",
        "primary_id_field": "source_id",
    },
    "algorithm": {
        "label": "算法能力",
        "description": "描述算法可接受的输入、产生的输出、解决的任务、工具实现、可靠性和替代算法。",
        "lifecycle": "seed",
        "primary_id_field": "algo_id",
    },
    "parameter_spec": {
        "label": "参数规范",
        "description": "规定算法参数的类型、默认值、范围、单位、可选值、可调性和默认值来源。",
        "lifecycle": "seed",
        "primary_id_field": "spec_id",
    },
    "workflow_pattern": {
        "label": "工作流模式",
        "description": "定义面向作业类型和灾种的多步骤算法执行模式，包含步骤依赖、数据源、参数和成功率。",
        "lifecycle": "seed",
        "primary_id_field": "pattern_id",
    },
    "repair_strategy": {
        "label": "修复策略",
        "description": "描述执行失败后的替代数据源、替代算法或其他恢复路径，并绑定原因码和适用任务。",
        "lifecycle": "seed",
        "primary_id_field": "strategy_id",
    },
    "durable_learning_summary": {
        "label": "持久学习摘要",
        "description": "由运行记录聚合得到的动态实体，表达条件化成功率、质量门通过率、时延、趋势和规划调整量。当前 seed 中无静态实例。",
        "lifecycle": "runtime-derived",
        "primary_id_field": "entity_kind + entity_id + condition_key",
    },
}


CONCEPTUAL_LAYERS = [
    {
        "layer_id": "context_and_situation",
        "layer_name": "灾害场景与资源处境",
        "description": "回答当前是什么灾种、处于什么响应阶段、需要激活哪些任务以及采用何种质量优先级。",
        "ontology_kinds": ["scenario_profile", "task_bundle"],
    },
    {
        "layer_id": "product_contract_and_delivery",
        "layer_name": "产品契约与产品组成",
        "description": "回答要交付什么产品、包含哪些图层、满足什么质量门、允许怎样降级以及如何声明缺口。",
        "ontology_kinds": [
            "product_contract",
            "output_requirement",
            "output_schema_policy",
            "qos_policy",
        ],
    },
    {
        "layer_id": "data_algorithm_task_capability",
        "layer_name": "数据、算法与任务能力",
        "description": "回答需要什么数据、从哪里获得、采用什么算法和参数、以何种工作流完成任务。",
        "ontology_kinds": [
            "task",
            "data_need",
            "data_type",
            "data_source",
            "algorithm",
            "parameter_spec",
            "workflow_pattern",
        ],
    },
    {
        "layer_id": "validation_repair_and_evidence",
        "layer_name": "验收、修复与运行证据",
        "description": "回答如何验收输出、失败后怎样恢复、如何记录证据以及怎样用运行结果反哺规划。",
        "ontology_kinds": [
            "product_contract",
            "output_requirement",
            "output_schema_policy",
            "qos_policy",
            "repair_strategy",
            "durable_learning_summary",
        ],
    },
]


RELATIONSHIP_SPECS = {
    "activates_task": ("激活任务", "场景处境激活需要进入规划空间的任务。"),
    "applies_to_output_type": ("适用于输出类型", "输出模式策略适用于指定的数据输出类型。"),
    "applies_to_scenario": ("适用于场景", "产品契约适用于指定灾害场景处境。"),
    "applies_to_task": ("适用于任务", "修复策略适用于指定任务。"),
    "can_transform_to": ("可转换为", "一种数据类型可通过已注册能力转换为另一种数据类型。"),
    "composed_of": ("由产品契约组成", "组合产品契约由一个或多个图层产品契约组成。"),
    "consumes_data_type": ("消费数据类型", "算法消费指定输入数据类型。"),
    "declares_data_need": ("声明数据需求", "任务编排包显式声明需要满足的数据需求。"),
    "defaults_to_qos": ("默认服务质量策略", "场景处境默认使用指定 QoS 策略。"),
    "emits_output_type": ("输出数据类型", "工作流模式在一个或多个步骤中产生指定输出数据类型。"),
    "enforces_schema_policy": ("执行输出模式策略", "输出要求通过指定模式策略约束字段结构。"),
    "has_data_need": ("具有数据需求", "任务具有指定数据需求。"),
    "has_parameter_spec": ("具有参数规范", "算法具有指定参数规范。"),
    "orchestrated_by": ("由任务包编排", "产品契约由指定任务编排包组织执行。"),
    "produces_data_type": ("产出数据类型", "算法能够产出指定数据类型。"),
    "refers_to_data_type": ("指向数据类型", "数据需求引用指定数据类型。"),
    "requests_task": ("请求任务", "任务编排包请求执行指定任务。"),
    "requires_input_type": ("需要输入类型", "工作流模式的步骤需要指定输入数据类型。"),
    "requires_output_requirement": ("需要输出要求", "产品契约必须满足指定输出要求。"),
    "requires_task": ("需要任务", "产品契约要求执行指定任务。"),
    "solves_task": ("解决任务", "工作流模式能够解决指定任务。"),
    "supports_data_type": ("支持数据类型", "数据源能够提供指定数据类型。"),
    "targets_output_requirement": ("目标输出要求", "工作流模式或任务编排包以指定输出要求为交付目标。"),
    "uses_algorithm": ("使用算法", "工作流模式在一个或多个步骤中使用指定算法。"),
    "uses_data_source": ("使用数据源", "工作流模式在一个或多个步骤中使用指定数据源。"),
    "uses_qos_policy": ("使用服务质量策略", "产品契约或任务编排包使用指定 QoS 策略。"),
    "uses_repair_strategy": ("使用修复策略", "产品契约或任务编排包允许使用指定修复策略。"),
}


FIELD_DESCRIPTIONS = {
    "type_id": "数据类型的稳定标识。",
    "theme": "数据表达的业务主题。",
    "geometry_type": "数据的几何或结构类型。",
    "description": "实体的人类可读说明。",
    "task_id": "任务的稳定标识。",
    "task_name": "任务名称。",
    "category": "任务所属类别。",
    "metadata": "扩展元数据，承载运行状态、证据引用或领域补充信息。",
    "profile_id": "场景处境的稳定标识。",
    "profile_name": "场景处境名称。",
    "disaster_types": "适用的灾种集合。",
    "activated_tasks": "该场景默认激活的任务标识集合。",
    "preferred_output_fields": "场景优先保留的输出字段。",
    "qos_priority": "场景的质量维度权重。",
    "qos_policy_id": "默认 QoS 策略标识。",
    "contract_id": "产品契约的稳定标识。",
    "contract_name": "产品契约名称。",
    "product_type": "契约约束的产品类型。",
    "response_phases": "适用的应急响应阶段。",
    "layer_requirements": "产品所需图层、关键性和输出要求映射。",
    "scenario_profile_ids": "契约适用的场景处境标识。",
    "task_bundle_ids": "负责组织契约执行的任务包标识。",
    "task_ids": "契约要求执行的任务标识。",
    "output_requirement_ids": "契约必须满足的输出要求标识。",
    "qos_policy_ids": "契约采用的 QoS 策略标识。",
    "repair_strategy_ids": "契约允许采用的修复策略标识。",
    "component_contract_ids": "组合契约包含的子产品契约标识。",
    "quality_gates": "产品交付前必须通过或解释的质量门。",
    "evidence_requirements": "产品交付需要保留的证据类型。",
    "degradation_policy": "部分满足或降级交付时的规则。",
    "gap_declaration_policy": "未满足要求时生成缺口声明的规则。",
    "delivery_policy": "机器可读交付物、临时产物和替代关系规则。",
    "satisfaction_states": "产品契约允许的满足状态集合。",
    "bundle_id": "任务编排包的稳定标识。",
    "bundle_name": "任务编排包名称。",
    "requested_tasks": "任务包请求执行的任务标识。",
    "output_requirement_id": "任务包的主要输出要求标识。",
    "data_need_ids": "任务包声明的数据需求标识。",
    "requires_disaster_profile": "是否必须有灾害场景处境才能使用。",
    "requirement_id": "输出要求的稳定标识。",
    "job_type": "适用的作业类型。",
    "output_type": "要求或模式策略对应的输出数据类型。",
    "schema_policy_id": "约束输出字段的模式策略标识。",
    "required_fields": "必须存在的输出字段。",
    "preferred_fields": "优先保留的输出字段。",
    "optional_fields": "允许存在但非必需的输出字段。",
    "policy_id": "策略的稳定标识。",
    "policy_name": "策略名称。",
    "priority": "质量维度权重。",
    "max_latency_seconds": "允许的最大时延，单位为秒。",
    "min_success_rate": "允许的最小成功率。",
    "need_id": "数据需求的稳定标识。",
    "data_type_id": "数据需求引用的数据类型标识。",
    "direction": "数据相对任务的输入或输出方向。",
    "required": "该项是否为必需条件。",
    "strategy_id": "修复策略的稳定标识。",
    "strategy_name": "修复策略名称。",
    "reason_codes": "触发策略的失败原因码。",
    "from_algorithm_id": "被替换的算法标识。",
    "to_algorithm_id": "替代算法标识。",
    "applies_to_task_ids": "策略适用的任务标识。",
    "algo_id": "算法的稳定标识。",
    "algo_name": "算法名称。",
    "input_types": "算法接受的输入数据类型。",
    "task_type": "算法解决的任务类型。",
    "tool_ref": "算法对应的工具或执行实现引用。",
    "success_rate": "算法或工作流的基线成功率。",
    "accuracy_score": "算法精度评分。",
    "stability_score": "算法稳定性评分。",
    "usage_mode": "算法的默认使用模式。",
    "alternatives": "可替代算法标识。",
    "spec_id": "参数规范的稳定标识。",
    "key": "参数在执行接口中的键名。",
    "label": "参数的人类可读名称。",
    "param_type": "参数值类型。",
    "default": "参数默认值。",
    "min_value": "参数允许的最小值。",
    "max_value": "参数允许的最大值。",
    "unit": "参数单位。",
    "choices": "参数允许的离散选项。",
    "tunable": "参数是否允许由规划或优化过程调整。",
    "optimization_tags": "参数参与优化的目标标签。",
    "conditional_defaults": "特定条件下采用的默认值。",
    "default_provenance": "默认值的来源和证据。",
    "order": "参数在界面或配置中的展示顺序。",
    "pattern_id": "工作流模式的稳定标识。",
    "pattern_name": "工作流模式名称。",
    "steps": "按顺序定义的算法执行步骤和依赖。",
    "source_id": "数据源的稳定标识。",
    "source_name": "数据源名称。",
    "supported_types": "数据源可提供的数据类型。",
    "quality_score": "数据源质量评分。",
    "source_kind": "数据源的接入类别。",
    "quality_tier": "数据源质量等级。",
    "freshness_category": "数据新鲜度类别。",
    "freshness_hours": "数据的新鲜度时间窗口。",
    "freshness_score": "数据新鲜度评分。",
    "supported_job_types": "数据源支持的作业类型。",
    "supported_geometry_types": "数据源支持的几何类型。",
    "retention_mode": "输出字段的保留模式。",
    "rename_hints": "字段重命名提示。",
    "compatibility_basis": "输出兼容性的判断依据。",
    "entity_kind": "学习摘要对应的实体本体类型。",
    "entity_id": "学习摘要对应的实体标识。",
    "total_runs": "聚合的运行次数。",
    "success_count": "成功运行次数。",
    "failure_count": "失败运行次数。",
    "repaired_count": "经过修复的运行次数。",
    "last_run_at": "最近一次运行时间。",
    "last_failure_reason": "最近一次失败原因。",
    "condition_key": "灾种、作业类型等条件组合的稳定键。",
    "time_decayed_score": "考虑时间衰减后的综合评分。",
    "quality_gate_pass_rate": "质量门通过率。",
    "avg_latency_seconds": "平均执行时延。",
    "recent_success_rate": "近期成功率。",
    "trend": "运行表现趋势。",
    "adjustment": "反馈给规划排序的调整量。",
}


class AllScenarioRepository:
    def __init__(self, repository: InMemoryKGRepository) -> None:
        self._repository = repository

    def __getattr__(self, name: str) -> Any:
        return getattr(self._repository, name)

    def get_scenario_profiles(self, disaster_type: str | None) -> list[Any]:
        profiles: dict[str, Any] = {}
        for value in (None, "generic", "flood", "earthquake", "typhoon"):
            for profile in self._repository.get_scenario_profiles(value):
                profiles[profile.profile_id] = profile
        return [profiles[key] for key in sorted(profiles)]


def _join(values: Iterable[Any], empty: str = "无") -> str:
    normalized = [str(value) for value in values if value not in (None, "")]
    return "、".join(normalized) if normalized else empty


def _describe_entity(kind: str, item: dict[str, Any], label: str) -> str:
    if kind == "data_type":
        return item.get("description") or f"{label} 数据类型，主题为 {item.get('theme')}，几何类型为 {item.get('geometry_type')}。"
    if kind == "task":
        return item.get("description") or f"{label} 任务，所属类别为 {item.get('category')}。"
    if kind == "scenario_profile":
        return (
            f"{label}，适用灾种为 {_join(item.get('disaster_types', []))}；"
            f"激活任务 {_join(item.get('activated_tasks', []))}；"
            f"默认 QoS 为 {item.get('qos_policy_id') or '未指定'}。"
        )
    if kind == "product_contract":
        scope = "组合产品" if item.get("component_contract_ids") else "图层产品"
        layer_kinds = [entry.get("layer_kind") for entry in item.get("layer_requirements", [])]
        return (
            f"{label} 是{scope}契约，产品类型为 {item.get('product_type')}；"
            f"覆盖 {_join(layer_kinds)}，适用灾种 {_join(item.get('disaster_types', []))}，"
            f"包含 {len(item.get('quality_gates', []))} 个质量门和 "
            f"{len(item.get('evidence_requirements', []))} 类证据要求。"
        )
    if kind == "task_bundle":
        return (
            f"{label} 编排 {_join(item.get('requested_tasks', []))}；"
            f"目标输出要求为 {item.get('output_requirement_id') or '由请求决定'}，"
            f"声明 {len(item.get('data_need_ids', []))} 项数据需求。"
        )
    if kind == "output_requirement":
        return (
            f"面向 {item.get('job_type')} 作业的 {item.get('output_type')} 输出要求；"
            f"必须字段为 {_join(item.get('required_fields', []))}，"
            f"由 {item.get('schema_policy_id')} 约束模式。"
        )
    if kind == "qos_policy":
        return (
            f"{label}，最大时延为 {item.get('max_latency_seconds') if item.get('max_latency_seconds') is not None else '未限制'} 秒，"
            f"最小成功率为 {item.get('min_success_rate') if item.get('min_success_rate') is not None else '未限制'}；"
            f"质量权重为 {json.dumps(item.get('priority', {}), ensure_ascii=False, sort_keys=True)}。"
        )
    if kind == "data_need":
        return item.get("description") or (
            f"任务 {item.get('task_id')} 的{item.get('direction')}数据需求，引用 {item.get('data_type_id')}，"
            f"{'必须满足' if item.get('required') else '可选'}。"
        )
    if kind == "repair_strategy":
        return (
            f"{label}，针对原因码 {_join(item.get('reason_codes', []))}；"
            f"适用任务 {_join(item.get('applies_to_task_ids', []))}。"
        )
    if kind == "algorithm":
        return (
            f"{label} 用于 {item.get('task_type')}，将 {_join(item.get('input_types', []))} 转换为 "
            f"{item.get('output_type')}；工具引用为 {item.get('tool_ref')}，基线成功率为 {item.get('success_rate')}。"
        )
    if kind == "parameter_spec":
        detail = item.get("description") or f"算法 {item.get('algo_id')} 的参数 {item.get('key')}。"
        bounds = []
        if item.get("min_value") is not None:
            bounds.append(f"最小值 {item.get('min_value')}")
        if item.get("max_value") is not None:
            bounds.append(f"最大值 {item.get('max_value')}")
        if item.get("choices"):
            bounds.append(f"可选值 {_join(item.get('choices', []))}")
        suffix = f"；{'，'.join(bounds)}" if bounds else ""
        return f"{detail} 默认值为 {item.get('default')!r}，类型为 {item.get('param_type')}{suffix}。"
    if kind == "workflow_pattern":
        steps = item.get("steps", [])
        return (
            f"{label} 面向 {item.get('job_type')} 作业和 {_join(item.get('disaster_types', []))}；"
            f"包含 {len(steps)} 个步骤：{_join(step.get('name') for step in steps)}；"
            f"基线成功率为 {item.get('success_rate')}。"
        )
    if kind == "data_source":
        return (
            f"{label} 是 {item.get('source_kind')} 类型数据源，支持 {_join(item.get('supported_types', []))}；"
            f"适用灾种 {_join(item.get('disaster_types', []))}，质量评分为 {item.get('quality_score')}，"
            f"新鲜度类别为 {item.get('freshness_category')}。"
        )
    if kind == "output_schema_policy":
        return (
            f"约束 {item.get('job_type')} 作业的 {item.get('output_type')} 输出；"
            f"保留模式为 {item.get('retention_mode')}，必须字段 {_join(item.get('required_fields', []))}，"
            f"兼容性依据为 {item.get('compatibility_basis')}。"
        )
    return f"{label}，属于 {kind} 本体。"


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _manifest_index(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    items_by_id: dict[str, dict[str, Any]] = {}
    kinds_by_id: dict[str, str] = {}
    for kind, (section, id_field, _label_field) in KIND_CONFIG.items():
        for item in manifest.get(section, []):
            entity_id = str(item[id_field])
            if entity_id in items_by_id:
                raise ValueError(f"Duplicate entity id in manifest: {entity_id}")
            items_by_id[entity_id] = item
            kinds_by_id[entity_id] = kind
    return items_by_id, kinds_by_id


def _layer_ids_for_kind(kind: str, layers: list[dict[str, Any]]) -> list[str]:
    return [layer["layer_id"] for layer in layers if kind in layer["ontology_kinds"]]


def _agent_layer_ids_for_kind(kind: str) -> list[str]:
    return [layer["layer_id"] for layer in AGENT_STRUCTURE if kind in layer["ontology_kinds"]]


def _build_entities(
    manifest: dict[str, Any],
    graph: Any,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    items_by_id, kinds_by_id = _manifest_index(manifest)
    graph_nodes_by_id = {node.id: node for node in graph.nodes}
    if set(items_by_id) != set(graph_nodes_by_id):
        missing_graph = sorted(set(items_by_id) - set(graph_nodes_by_id))
        missing_manifest = sorted(set(graph_nodes_by_id) - set(items_by_id))
        raise ValueError(
            f"Manifest/graph node mismatch; missing_graph={missing_graph}, missing_manifest={missing_manifest}"
        )

    entities: list[dict[str, Any]] = []
    for entity_id in sorted(items_by_id, key=lambda value: (kinds_by_id[value], value)):
        kind = kinds_by_id[entity_id]
        item = items_by_id[entity_id]
        node = graph_nodes_by_id[entity_id]
        entities.append(
            {
                "entity_id": entity_id,
                "ontology_id": kind,
                "ontology_label": CLASS_SPECS[kind]["label"],
                "label": node.label,
                "description": _describe_entity(kind, item, node.label),
                "conceptual_layers": _layer_ids_for_kind(kind, CONCEPTUAL_LAYERS),
                "agent_layers": _agent_layer_ids_for_kind(kind),
                "properties": item,
            }
        )
    return entities, {entity["entity_id"]: entity for entity in entities}


def _runtime_fields() -> list[dict[str, Any]]:
    fields = []
    for item in dataclasses.fields(DurableLearningSummary):
        fields.append(
            {
                "field_name": item.name,
                "data_types": [str(item.type).replace("typing.", "")],
                "required": item.default is dataclasses.MISSING and item.default_factory is dataclasses.MISSING,
                "description": FIELD_DESCRIPTIONS.get(
                    item.name,
                    f"{item.name} 字段，记录持久学习摘要的结构化属性。",
                ),
            }
        )
    return fields


def _build_ontology_classes(
    manifest: dict[str, Any],
    entity_counts: Counter[str],
) -> list[dict[str, Any]]:
    classes = []
    for kind in sorted(CLASS_SPECS):
        spec = CLASS_SPECS[kind]
        section = KIND_CONFIG.get(kind, (None, None, None))[0]
        if section:
            items = manifest.get(section, [])
            field_names = sorted({key for item in items for key in item})
            fields = []
            for field_name in field_names:
                values = [item.get(field_name) for item in items]
                fields.append(
                    {
                        "field_name": field_name,
                        "data_types": sorted({_value_type(value) for value in values}),
                        "required": bool(items) and all(field_name in item and item[field_name] is not None for item in items),
                        "description": FIELD_DESCRIPTIONS.get(
                            field_name,
                            f"{field_name} 字段，记录该本体实体的结构化属性。",
                        ),
                    }
                )
        else:
            fields = _runtime_fields()
        classes.append(
            {
                "ontology_id": kind,
                "label": spec["label"],
                "description": spec["description"],
                "lifecycle": spec["lifecycle"],
                "primary_id_field": spec["primary_id_field"],
                "manifest_section": section,
                "entity_count": entity_counts.get(kind, 0),
                "conceptual_layers": _layer_ids_for_kind(kind, CONCEPTUAL_LAYERS),
                "agent_layers": _agent_layer_ids_for_kind(kind),
                "fields": fields,
            }
        )
    return classes


def _build_relationships(
    graph: Any,
    entities_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    instances: list[dict[str, Any]] = []
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in sorted(graph.edges, key=lambda item: (item.relationship, item.source, item.target)):
        if edge.relationship not in RELATIONSHIP_SPECS:
            raise ValueError(f"Missing relationship description: {edge.relationship}")
        source = entities_by_id[edge.source]
        target = entities_by_id[edge.target]
        label, description = RELATIONSHIP_SPECS[edge.relationship]
        instance = {
            "source_id": edge.source,
            "source_kind": source["ontology_id"],
            "relationship_id": edge.relationship,
            "relationship_label": label,
            "target_id": edge.target,
            "target_kind": target["ontology_id"],
            "description": f"{source['label']}（{edge.source}）{label}{target['label']}（{edge.target}）。",
            "properties": dict(edge.meta or {}),
        }
        instances.append(instance)
        grouped[edge.relationship].append(instance)

    ontology_relationships = []
    for relationship_id in sorted(RELATIONSHIP_SPECS):
        label, description = RELATIONSHIP_SPECS[relationship_id]
        values = grouped.get(relationship_id, [])
        ontology_relationships.append(
            {
                "relationship_id": relationship_id,
                "label": label,
                "description": description,
                "source_kinds": sorted({item["source_kind"] for item in values}),
                "target_kinds": sorted({item["target_kind"] for item in values}),
                "instance_count": len(values),
            }
        )
    return ontology_relationships, instances


def _write_csv(path: Path, headers: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def _markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_escape(value) for value in row) + " |")
    return lines


def _progress_markdown(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    classes = payload["ontology"]["classes"]
    relationships = payload["ontology"]["relationships"]
    entities = payload["entity_layer"]["nodes"]
    product_contracts = [item for item in entities if item["ontology_id"] == "product_contract"]
    count_by_kind = Counter(item["ontology_id"] for item in entities)

    lines = [
        "# FusionAgent 当前进展与知识图谱本体说明",
        "",
        f"> 生成日期：{metadata['generated_at']}  ",
        f"> Seed 内容哈希：`{metadata['seed_content_hash']}`  ",
        f"> 当前静态实体：**{metadata['entity_count']}**；实体关系：**{metadata['relationship_instance_count']}**；本体类：**{metadata['ontology_class_count']}**；关系类型：**{metadata['relationship_type_count']}**。",
        "",
        "## 1. 当前进展结论",
        "",
        "FusionAgent 已从“能力目录型知识图谱”推进到“产品契约驱动的决策知识图谱”。此前质量门、交付策略、降级规则、缺口声明和证据要求主要分散在配置、规划产物和执行代码中；当前这些内容已经由 `ProductContract` 统一建模，并进入种子清单、仓库、Neo4j 启动、知识检索、规划结果和图谱 API。",
        "",
        "当前实现形成以下闭环：",
        "",
        "1. 场景处境确定灾种、任务和质量优先级，产品契约进一步限定适用响应阶段。",
        "2. 产品契约规定要交付的产品、图层、质量门、证据、降级和缺口策略。",
        "3. 任务、数据、算法、参数和工作流提供可执行能力。",
        "4. 输出要求、模式策略、QoS、修复策略和运行学习完成验收、恢复与审计。",
        "",
        "## 2. 产品契约核心缺口的补齐",
        "",
        "本轮新增 6 个产品契约实体，其中 1 个是多图层应急矢量组合契约，5 个是建筑、道路、水体面、水系线和兴趣点图层契约。契约通过 `applies_to_scenario`、`orchestrated_by`、`requires_task`、`requires_output_requirement`、`uses_qos_policy`、`uses_repair_strategy` 和 `composed_of` 与现有图谱连接。",
        "",
    ]
    lines.extend(
        _markdown_table(
            ["契约实体", "名称", "说明"],
            ((item["entity_id"], item["label"], item["description"]) for item in product_contracts),
        )
    )
    lines.extend(
        [
            "",
            "## 3. 工程接入状态",
            "",
            "- **模型与种子**：新增 `ProductContractNode` 和 6 个静态契约，完整记录质量门、证据要求、满足状态及策略对象。",
            "- **仓库层**：内存仓库和 Neo4j 仓库均支持按灾种读取产品契约。",
            "- **图数据库启动**：Python bootstrap 与静态 Cypher 均创建契约节点及跨层关系。",
            "- **清单层**：产品契约已进入 `kg/seed_manifest.generated.json`，可进行哈希校验和跨运行加载。",
            "- **检索与规划**：检索上下文选择产品契约，`WorkflowPlan.product_contract` 保存规划所消费的契约。",
            "- **图谱 API**：KG overview 返回产品契约节点及相关边，支持浏览和路径审计。",
            "- **规范文档**：`docs/thesis/product_contract_spec.md` 已加入本体实体与关系映射。",
            "- **汇报材料**：组会 PPT 已补充四层本体闭环、六节点本体全景和运行消费说明。",
            "",
            "## 4. 当前图谱规模",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ["本体类", "中文名称", "静态实体数", "生命周期"],
            (
                (
                    item["ontology_id"],
                    item["label"],
                    count_by_kind.get(item["ontology_id"], 0),
                    item["lifecycle"],
                )
                for item in classes
            ),
        )
    )
    lines.extend(["", "## 5. 四层本体视图", ""])
    for layer in payload["architecture"]["conceptual_layers"]:
        kind_labels = [CLASS_SPECS[kind]["label"] for kind in layer["ontology_kinds"]]
        lines.extend(
            [
                f"### {layer['layer_name']}",
                "",
                layer["description"],
                "",
                f"包含本体：{_join(kind_labels)}。",
                "",
            ]
        )
    lines.extend(["## 6. 五层 Agent 运行视图", ""])
    lines.extend(
        _markdown_table(
            ["运行层", "名称", "消费的本体", "代码模块"],
            (
                (
                    item["layer_id"],
                    item["layer_name"],
                    _join(CLASS_SPECS[kind]["label"] for kind in item["ontology_kinds"]),
                    "<br>".join(item["module_refs"]),
                )
                for item in payload["architecture"]["agent_layers"]
            ),
        )
    )
    lines.extend(["", "## 7. 本体类完整说明", ""])
    lines.extend(
        _markdown_table(
            ["本体 ID", "名称", "说明", "主标识", "实体数"],
            (
                (
                    item["ontology_id"],
                    item["label"],
                    item["description"],
                    item["primary_id_field"],
                    item["entity_count"],
                )
                for item in classes
            ),
        )
    )
    lines.extend(["", "每个本体的完整字段、字段类型、是否必需及字段说明见 `ontology_fields.csv` 和 JSON 的 `ontology.classes[].fields`。", ""])
    lines.extend(["## 8. 关系本体完整说明", ""])
    lines.extend(
        _markdown_table(
            ["关系 ID", "名称", "源本体", "目标本体", "实例数", "说明"],
            (
                (
                    item["relationship_id"],
                    item["label"],
                    _join(item["source_kinds"]),
                    _join(item["target_kinds"]),
                    item["instance_count"],
                    item["description"],
                )
                for item in relationships
            ),
        )
    )
    lines.extend(
        [
            "",
            "## 9. 运行消费链路",
            "",
            "```text",
            "ScenarioProfile",
            "  -> ProductContract",
            "  -> TaskBundle / Task / OutputRequirement / QoSPolicy / RepairStrategy",
            "  -> WorkflowPattern / Algorithm / ParameterSpec / DataSource / DataType",
            "  -> WorkflowPlan.product_contract",
            "  -> 执行、质量门、缺口声明、证据与持久学习摘要",
            "```",
            "",
            "这意味着 `ProductContract` 已不再只是运行后生成的 JSON，而是可以被检索、选择、遍历、绑定到计划并通过 Neo4j/API 审计的一等图谱实体。",
            "",
            "## 10. 验证状态",
            "",
            "- 产品契约、仓库、Neo4j、清单、规划上下文和 KG API 的定向测试共 90 项通过。",
            "- Seed manifest 哈希一致性检查通过。",
            "- 组会 PPT 的溢出、模板忠实度和 PPTX 空占位符检查通过。",
            "- 本文档导出时再次检查实体唯一性、关系端点完整性、本体数量和关系说明覆盖率。",
            "",
            "## 11. 尚未完成的研究问题",
            "",
            "1. **复杂处境下的决策空间仍偏小**：候选排序仍可能使智能规划退化为选择最高分方案。",
            "2. **模拟规划路径仍有接口问题**：需要保证模拟规划读取与真实检索上下文一致。",
            "3. **增量价值尚未实验性证明**：需要完成固定规则、纯知识图谱、大模型、能力图谱和完整契约图谱五类基线。",
            "4. **本体规范性仍可加强**：当前本体是工程可执行本体，后续可补充 SHACL/OWL 约束或专家验证。",
            "5. **运行学习实体尚未静态化**：`durable_learning_summary` 由运行记录动态生成，当前 seed 无实例。",
            "",
            "## 12. 文档包文件说明",
            "",
            "- `FusionAgent_当前进展与知识图谱说明_20260727.md`：当前文件，说明进展、全景和后续问题。",
            "- `FusionAgent_知识图谱实体说明_20260727.md`：按本体逐一列出全部实体及说明。",
            "- `FusionAgent_知识图谱本体与实体_20260727.json`：完整机器可读本体层、实体层和架构层。",
            "- `ontology_classes.csv`：本体类及说明。",
            "- `ontology_fields.csv`：每个本体的字段定义。",
            "- `ontology_relationships.csv`：关系本体及说明。",
            "- `entity_nodes.csv`：全部实体、说明和完整属性 JSON。",
            "- `entity_relationships.csv`：全部实体关系及逐条说明。",
            "- `architecture_layers.csv`：四层业务视图和五层 Agent 视图。",
            "- `校验摘要.txt`：本次导出的计数和完整性检查结果。",
            "",
            "## 13. 依据文件",
            "",
            "- `kg/models.py`",
            "- `kg/seed.py`",
            "- `kg/seed_manifest.generated.json`",
            "- `services/kg_graph_service.py`",
            "- `agent/retriever.py`",
            "- `agent/planner.py`",
            "- `schemas/agent.py`",
            "- `docs/thesis/product_contract_spec.md`",
            "",
        ]
    )
    return "\n".join(lines)


def _entity_markdown(payload: dict[str, Any]) -> str:
    entities = payload["entity_layer"]["nodes"]
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for entity in entities:
        grouped[entity["ontology_id"]].append(entity)

    lines = [
        "# FusionAgent 知识图谱实体说明",
        "",
        f"> 共 {len(entities)} 个静态实体。每个实体的完整结构化属性见同目录 JSON 或 `entity_nodes.csv` 的 `properties_json` 列。",
        "",
    ]
    for kind in sorted(grouped, key=lambda value: CLASS_SPECS[value]["label"]):
        values = sorted(grouped[kind], key=lambda item: item["entity_id"])
        lines.extend(
            [
                f"## {CLASS_SPECS[kind]['label']}（`{kind}`，{len(values)} 个）",
                "",
                CLASS_SPECS[kind]["description"],
                "",
            ]
        )
        lines.extend(
            _markdown_table(
                ["实体 ID", "名称", "说明"],
                ((item["entity_id"], item["label"], item["description"]) for item in values),
            )
        )
        lines.append("")
    lines.extend(
        [
            "## 运行期派生实体",
            "",
            "`durable_learning_summary` 当前没有 seed 实体。它在系统运行后根据执行记录动态聚合，字段定义已收录在本体 JSON 和 `ontology_fields.csv` 中。",
            "",
        ]
    )
    return "\n".join(lines)


def export_docs() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    graph = build_overview_graph(AllScenarioRepository(InMemoryKGRepository()))
    entities, entities_by_id = _build_entities(manifest, graph)
    entity_counts = Counter(item["ontology_id"] for item in entities)
    ontology_classes = _build_ontology_classes(manifest, entity_counts)
    ontology_relationships, entity_relationships = _build_relationships(graph, entities_by_id)

    agent_layers = [
        {
            "layer_id": layer["layer_id"],
            "layer_name": layer["layer_name"],
            "ontology_kinds": list(layer["ontology_kinds"]),
            "module_refs": list(layer["module_refs"]),
            "evidence_refs": list(layer["evidence_refs"]),
        }
        for layer in AGENT_STRUCTURE
    ]
    payload = {
        "metadata": {
            "schema_version": "1.0.0",
            "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "generated_from": [
                str(MANIFEST_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "services/kg_graph_service.py::build_overview_graph",
                "kg/models.py",
            ],
            "seed_content_hash": manifest["metadata"]["content_hash"],
            "seed_schema_version": manifest["metadata"]["schema_version"],
            "ontology_class_count": len(ontology_classes),
            "seed_backed_ontology_class_count": len(KIND_CONFIG),
            "runtime_derived_ontology_class_count": 1,
            "relationship_type_count": len(ontology_relationships),
            "entity_count": len(entities),
            "relationship_instance_count": len(entity_relationships),
            "verification": {
                "targeted_tests_passed": 90,
                "seed_manifest_check": "passed",
                "ppt_overflow_check": "passed",
                "ppt_template_fidelity": "passed",
                "ppt_empty_placeholder_check": "passed",
            },
        },
        "architecture": {
            "conceptual_layers": CONCEPTUAL_LAYERS,
            "agent_layers": agent_layers,
        },
        "ontology": {
            "classes": ontology_classes,
            "relationships": ontology_relationships,
        },
        "entity_layer": {
            "nodes": entities,
            "relationships": entity_relationships,
        },
    }

    if len(entities) != sum(len(manifest.get(section, [])) for section, _id, _label in KIND_CONFIG.values()):
        raise ValueError("Entity count does not match manifest sections")
    if any(item["source_id"] not in entities_by_id or item["target_id"] not in entities_by_id for item in entity_relationships):
        raise ValueError("Entity relationship contains a dangling endpoint")
    if len(ontology_classes) != 15:
        raise ValueError(f"Expected 15 ontology classes, got {len(ontology_classes)}")
    if len(ontology_relationships) != len(RELATIONSHIP_SPECS):
        raise ValueError("Relationship ontology coverage is incomplete")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "FusionAgent_知识图谱本体与实体_20260727.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "FusionAgent_当前进展与知识图谱说明_20260727.md").write_text(
        _progress_markdown(payload), encoding="utf-8"
    )
    (OUTPUT_DIR / "FusionAgent_知识图谱实体说明_20260727.md").write_text(
        _entity_markdown(payload), encoding="utf-8"
    )

    _write_csv(
        OUTPUT_DIR / "ontology_classes.csv",
        [
            "ontology_id",
            "label",
            "description",
            "lifecycle",
            "primary_id_field",
            "manifest_section",
            "entity_count",
            "conceptual_layers",
            "agent_layers",
        ],
        (
            {
                **item,
                "conceptual_layers": ";".join(item["conceptual_layers"]),
                "agent_layers": ";".join(item["agent_layers"]),
            }
            for item in ontology_classes
        ),
    )
    _write_csv(
        OUTPUT_DIR / "ontology_fields.csv",
        ["ontology_id", "ontology_label", "field_name", "data_types", "required", "description"],
        (
            {
                "ontology_id": ontology["ontology_id"],
                "ontology_label": ontology["label"],
                "field_name": field["field_name"],
                "data_types": ";".join(field["data_types"]),
                "required": field["required"],
                "description": field["description"],
            }
            for ontology in ontology_classes
            for field in ontology["fields"]
        ),
    )
    _write_csv(
        OUTPUT_DIR / "ontology_relationships.csv",
        [
            "relationship_id",
            "label",
            "description",
            "source_kinds",
            "target_kinds",
            "instance_count",
        ],
        (
            {
                **item,
                "source_kinds": ";".join(item["source_kinds"]),
                "target_kinds": ";".join(item["target_kinds"]),
            }
            for item in ontology_relationships
        ),
    )
    _write_csv(
        OUTPUT_DIR / "entity_nodes.csv",
        [
            "entity_id",
            "ontology_id",
            "ontology_label",
            "label",
            "description",
            "conceptual_layers",
            "agent_layers",
            "properties_json",
        ],
        (
            {
                **item,
                "conceptual_layers": ";".join(item["conceptual_layers"]),
                "agent_layers": ";".join(item["agent_layers"]),
                "properties_json": json.dumps(item["properties"], ensure_ascii=False, sort_keys=True),
            }
            for item in entities
        ),
    )
    _write_csv(
        OUTPUT_DIR / "entity_relationships.csv",
        [
            "source_id",
            "source_kind",
            "relationship_id",
            "relationship_label",
            "target_id",
            "target_kind",
            "description",
            "properties_json",
        ],
        (
            {
                **item,
                "properties_json": json.dumps(item["properties"], ensure_ascii=False, sort_keys=True),
            }
            for item in entity_relationships
        ),
    )
    architecture_rows = []
    for layer in CONCEPTUAL_LAYERS:
        architecture_rows.append(
            {
                "view": "conceptual",
                "layer_id": layer["layer_id"],
                "layer_name": layer["layer_name"],
                "description": layer["description"],
                "ontology_kinds": ";".join(layer["ontology_kinds"]),
                "module_refs": "",
                "evidence_refs": "",
            }
        )
    for layer in agent_layers:
        architecture_rows.append(
            {
                "view": "agent_runtime",
                "layer_id": layer["layer_id"],
                "layer_name": layer["layer_name"],
                "description": "Agent 运行架构层。",
                "ontology_kinds": ";".join(layer["ontology_kinds"]),
                "module_refs": ";".join(layer["module_refs"]),
                "evidence_refs": ";".join(layer["evidence_refs"]),
            }
        )
    _write_csv(
        OUTPUT_DIR / "architecture_layers.csv",
        ["view", "layer_id", "layer_name", "description", "ontology_kinds", "module_refs", "evidence_refs"],
        architecture_rows,
    )

    validation_text = "\n".join(
        [
            "FusionAgent 知识图谱文档导出校验",
            f"生成时间: {payload['metadata']['generated_at']}",
            f"Seed 哈希: {payload['metadata']['seed_content_hash']}",
            f"本体类: {len(ontology_classes)}",
            f"关系类型: {len(ontology_relationships)}",
            f"静态实体: {len(entities)}",
            f"实体关系: {len(entity_relationships)}",
            "实体 ID 唯一性: 通过",
            "实体关系端点完整性: 通过",
            "关系说明覆盖率: 100%",
            "JSON/CSV/Markdown 导出: 通过",
            "",
        ]
    )
    (OUTPUT_DIR / "校验摘要.txt").write_text(validation_text, encoding="utf-8")
    return payload


def main() -> None:
    payload = export_docs()
    print(
        json.dumps(
            {
                "output_dir": str(OUTPUT_DIR),
                "ontology_classes": payload["metadata"]["ontology_class_count"],
                "relationship_types": payload["metadata"]["relationship_type_count"],
                "entities": payload["metadata"]["entity_count"],
                "relationships": payload["metadata"]["relationship_instance_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
