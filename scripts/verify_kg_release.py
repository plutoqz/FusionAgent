from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


VERIFIER_ID = "fusionagent.kg-release-verifier.v1"
REPORT_SCHEMA_VERSION = "1.0.0"
REQUIRED_RELEASE_FILES = {"schema.json", "entities.json", "policies.json"}
EXPECTED_LAYER_IDS = {f"L{index}" for index in range(1, 8)}
REQUIRED_CONSTRAINT_IDS = {
    "C-ID-UNIQUE",
    "C-REF-CLOSED",
    "C-WORKFLOW-DAG",
    "C-ALGO-IO",
    "C-CONTRACT-CLOSED",
    "C-STRICT-REQUIRED",
    "C-RELEASE-IMMUTABLE",
    "C-EXPERIENCE-SEPARATE",
}
REQUIRED_CQ_IDS = {f"CQ{index:02d}" for index in range(1, 9)}

ENTITY_SECTION_IDS = {
    "data_types": "type_id",
    "tasks": "task_id",
    "scenario_profiles": "profile_id",
    "product_contracts": "contract_id",
    "task_bundles": "bundle_id",
    "output_requirements": "requirement_id",
    "qos_policies": "policy_id",
    "data_needs": "need_id",
    "repair_strategies": "strategy_id",
    "algorithms": "algo_id",
    "parameter_specs": "spec_id",
    "workflow_patterns": "pattern_id",
    "data_sources": "source_id",
    "output_schema_policies": "policy_id",
}

POLICY_LIST_SECTIONS = {
    "disaster_vocabulary",
    "place_vocabulary",
    "task_semantics",
    "output_contracts",
    "quality_policies",
    "source_role_policies",
    "source_bundle_policies",
    "quality_component_policies",
    "decision_policies",
}

POLICY_OBJECT_SECTIONS = {
    "metadata",
    "mission_policy",
    "quality_check_templates",
    "quality_adaptation_policy",
    "source_runtime_bindings",
    "artifact_evaluation_policy",
    "fault_policy",
    "recovery_policy",
    "runtime_gates",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _semantic_hash(
    schema: dict[str, Any], entities: dict[str, Any], policies: dict[str, Any]
) -> str:
    payload = [schema, entities, policies]
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _embedded_entity_hash(entities: dict[str, Any]) -> str:
    normalized = json.loads(json.dumps(entities, ensure_ascii=False, sort_keys=True))
    metadata = dict(normalized.get("metadata") or {})
    metadata["content_hash"] = ""
    metadata["generated_at"] = ""
    normalized["metadata"] = metadata
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(normalized)).hexdigest()


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"无法读取 {path.name}: {exc}"
    except UnicodeDecodeError as exc:
        return None, f"{path.name} 不是有效 UTF-8: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"{path.name} 不是有效 JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path.name} 顶层必须是 JSON object"
    return payload, None


def _check(
    check_id: str, title: str, errors: Iterable[str], **details: Any
) -> dict[str, Any]:
    normalized_errors = list(
        dict.fromkeys(str(error) for error in errors if str(error))
    )
    return {
        "id": check_id,
        "title": title,
        "passed": not normalized_errors,
        "errors": normalized_errors,
        "details": details,
    }


def _metadata_errors(
    payload: dict[str, Any] | None,
    *,
    filename: str,
    release: dict[str, Any] | None,
) -> list[str]:
    if payload is None:
        return [f"无法校验 {filename} metadata：文件未成功解析"]
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return [f"{filename}.metadata 缺失或不是 object"]
    errors: list[str] = []
    if metadata.get("status") != "frozen":
        errors.append(f"{filename}.metadata.status 必须为 frozen")
    if release is not None:
        if metadata.get("release_id") != release.get("release_id"):
            errors.append(f"{filename}.metadata.release_id 与 release.json 不一致")
        expected_version = (
            release.get("ontology_version")
            if filename == "schema.json"
            else release.get("knowledge_version")
        )
        version_key = (
            "ontology_version" if filename == "schema.json" else "knowledge_version"
        )
        if metadata.get(version_key) != expected_version:
            errors.append(f"{filename}.metadata.{version_key} 与 release.json 不一致")
    return errors


def _validate_release_status(
    release: dict[str, Any] | None, parse_error: str | None
) -> dict[str, Any]:
    errors: list[str] = []
    if parse_error:
        errors.append(parse_error)
    if release is not None:
        if release.get("status") != "frozen":
            errors.append("release.status 必须为 frozen")
        for key in ("release_id", "ontology_version", "knowledge_version", "frozen_at"):
            if (
                not isinstance(release.get(key), str)
                or not str(release.get(key)).strip()
            ):
                errors.append(f"release.{key} 必须是非空字符串")
        for key in ("semantic_hash", "experience_snapshot_hash"):
            value = release.get(key)
            if (
                not isinstance(value, str)
                or not value.startswith("sha256:")
                or len(value) != 71
            ):
                errors.append(f"release.{key} 必须是 sha256:<64 hex>")
    return _check(
        "release_status",
        "冻结发布状态",
        errors,
        release_id=release.get("release_id") if release else None,
        ontology_version=release.get("ontology_version") if release else None,
        knowledge_version=release.get("knowledge_version") if release else None,
        status=release.get("status") if release else None,
    )


def _validate_file_hashes(root: Path, release: dict[str, Any] | None) -> dict[str, Any]:
    errors: list[str] = []
    actual_hashes: dict[str, str | None] = {}
    files = release.get("files") if release else None
    if not isinstance(files, dict):
        errors.append("release.files 缺失或不是 object")
        files = {}
    missing_declarations = sorted(
        REQUIRED_RELEASE_FILES - set(str(key) for key in files)
    )
    if missing_declarations:
        errors.append(f"release.files 缺少冻结文件: {', '.join(missing_declarations)}")
    for relative_path, expected_hash in sorted(
        files.items(), key=lambda item: str(item[0])
    ):
        name = str(relative_path)
        target = (root / name).resolve()
        if target.parent != root:
            errors.append(f"冻结文件路径越界: {name}")
            actual_hashes[name] = None
            continue
        if not target.is_file():
            errors.append(f"冻结文件不存在: {name}")
            actual_hashes[name] = None
            continue
        actual_hash = _sha256_file(target)
        actual_hashes[name] = actual_hash
        if expected_hash != actual_hash:
            errors.append(
                f"{name} 逐字节 SHA-256 不匹配: expected={expected_hash}, actual={actual_hash}"
            )
    return _check(
        "file_hashes",
        "冻结文件逐字节 SHA-256",
        errors,
        declared_files=sorted(str(key) for key in files),
        actual_hashes=actual_hashes,
    )


def _validate_semantic_hash(
    release: dict[str, Any] | None,
    schema: dict[str, Any] | None,
    entities: dict[str, Any] | None,
    policies: dict[str, Any] | None,
) -> dict[str, Any]:
    errors: list[str] = []
    actual: str | None = None
    if release is None or schema is None or entities is None or policies is None:
        errors.append(
            "release/schema/entities/policies 未全部成功解析，无法计算语义哈希"
        )
    else:
        actual = _semantic_hash(schema, entities, policies)
        if actual != release.get("semantic_hash"):
            errors.append(
                f"语义哈希不匹配: expected={release.get('semantic_hash')}, actual={actual}"
            )
    return _check(
        "semantic_hash",
        "规范化语义哈希",
        errors,
        expected=release.get("semantic_hash") if release else None,
        actual=actual,
    )


def _schema_inventory(
    schema: dict[str, Any] | None
) -> tuple[dict[str, str], list[str], dict[str, Any]]:
    class_layers: dict[str, str] = {}
    errors: list[str] = []
    details: dict[str, Any] = {"layers": {}, "class_count": 0}
    if schema is None:
        return class_layers, ["schema.json 未成功解析"], details
    layers = schema.get("layers")
    if not isinstance(layers, list):
        return class_layers, ["schema.layers 缺失或不是 list"], details
    seen_layers: set[str] = set()
    for layer_index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            errors.append(f"schema.layers[{layer_index}] 不是 object")
            continue
        layer_id = str(layer.get("id") or "")
        if not layer_id:
            errors.append(f"schema.layers[{layer_index}].id 缺失")
            continue
        if layer_id in seen_layers:
            errors.append(f"重复层级 ID: {layer_id}")
        seen_layers.add(layer_id)
        for name_field in ("name_zh", "name_en"):
            if (
                not isinstance(layer.get(name_field), str)
                or not str(layer.get(name_field)).strip()
            ):
                errors.append(f"{layer_id}.{name_field} 必须是非空字符串")
        classes = layer.get("classes")
        if not isinstance(classes, list) or not classes:
            errors.append(f"{layer_id}.classes 必须是非空 list")
            continue
        layer_class_ids: list[str] = []
        for class_index, concept in enumerate(classes):
            if not isinstance(concept, dict):
                errors.append(f"{layer_id}.classes[{class_index}] 不是 object")
                continue
            class_id = str(concept.get("id") or "")
            if not class_id:
                errors.append(f"{layer_id}.classes[{class_index}].id 缺失")
                continue
            if class_id in class_layers:
                errors.append(
                    f"本体类 {class_id} 同时出现在 {class_layers[class_id]} 和 {layer_id}"
                )
            status = concept.get("status")
            if status not in {"implemented", "runtime-derived", "reserved"}:
                errors.append(
                    f"本体类 {class_id} 的 status 必须是 implemented/runtime-derived/reserved"
                )
            class_layers[class_id] = layer_id
            layer_class_ids.append(class_id)
        details["layers"][layer_id] = layer_class_ids
    missing_layers = sorted(EXPECTED_LAYER_IDS - seen_layers)
    extra_layers = sorted(seen_layers - EXPECTED_LAYER_IDS)
    if missing_layers:
        errors.append(f"缺少七层本体层级: {', '.join(missing_layers)}")
    if extra_layers:
        errors.append(f"存在非 v1 七层层级: {', '.join(extra_layers)}")
    details["class_count"] = len(class_layers)
    details["layer_ids"] = sorted(seen_layers)
    return class_layers, errors, details


def _validate_schema_layers(
    schema: dict[str, Any] | None, release: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, str]]:
    class_layers, errors, details = _schema_inventory(schema)
    errors.extend(_metadata_errors(schema, filename="schema.json", release=release))
    if schema is not None:
        constraints = schema.get("constraints")
        constraint_ids: list[str] = []
        if not isinstance(constraints, list):
            errors.append("schema.constraints 缺失或不是 list")
        else:
            for index, constraint in enumerate(constraints):
                if not isinstance(constraint, dict) or not constraint.get("id"):
                    errors.append(f"schema.constraints[{index}] 缺少 ID")
                    continue
                constraint_ids.append(str(constraint["id"]))
            duplicates = sorted(
                {value for value in constraint_ids if constraint_ids.count(value) > 1}
            )
            if duplicates:
                errors.append(f"重复约束 ID: {', '.join(duplicates)}")
            missing = sorted(REQUIRED_CONSTRAINT_IDS - set(constraint_ids))
            if missing:
                errors.append(f"缺少 v1 必要约束: {', '.join(missing)}")
        details["constraint_ids"] = sorted(set(constraint_ids))
    return (
        _check("schema_layers", "七层本体与基础约束", errors, **details),
        class_layers,
    )


def _validate_schema_references(
    schema: dict[str, Any] | None, class_layers: dict[str, str]
) -> dict[str, Any]:
    errors: list[str] = []
    relation_ids: list[str] = []
    property_ids: list[str] = []
    mapping_count = 0
    if schema is None:
        errors.append("schema.json 未成功解析")
        relations: list[Any] = []
    else:
        value = schema.get("relations")
        if not isinstance(value, list):
            errors.append("schema.relations 缺失或不是 list")
            relations = []
        else:
            relations = value
    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            errors.append(f"schema.relations[{index}] 不是 object")
            continue
        relation_id = str(relation.get("id") or "")
        if not relation_id:
            errors.append(f"schema.relations[{index}].id 缺失")
        else:
            relation_ids.append(relation_id)
        for endpoint in ("from", "to"):
            concept = str(relation.get(endpoint) or "")
            if concept not in class_layers:
                errors.append(
                    f"关系 {relation_id or index} 的 {endpoint} 引用未声明本体类: {concept or '<empty>'}"
                )
    duplicates = sorted(
        {value for value in relation_ids if relation_ids.count(value) > 1}
    )
    if duplicates:
        errors.append(f"重复关系 ID: {', '.join(duplicates)}")

    if schema is not None:
        properties = schema.get("properties")
        if not isinstance(properties, list):
            errors.append("schema.properties 缺失或不是 list")
        else:
            for index, property_spec in enumerate(properties):
                if not isinstance(property_spec, dict):
                    errors.append(f"schema.properties[{index}] 不是 object")
                    continue
                property_id = str(property_spec.get("id") or "")
                if not property_id:
                    errors.append(f"schema.properties[{index}].id 缺失")
                else:
                    property_ids.append(property_id)
                domains = property_spec.get("domain")
                if not isinstance(domains, list) or not domains:
                    errors.append(
                        f"schema.properties[{property_id or index}].domain 必须是非空 list"
                    )
                    continue
                for concept in domains:
                    if str(concept) not in class_layers:
                        errors.append(
                            f"属性 {property_id or index} 的 domain 引用未声明本体类: {concept}"
                        )
            duplicates = sorted(
                {value for value in property_ids if property_ids.count(value) > 1}
            )
            if duplicates:
                errors.append(f"重复属性 ID: {', '.join(duplicates)}")

        identity_policy = schema.get("identity_policy")
        if not isinstance(identity_policy, dict):
            errors.append("schema.identity_policy 缺失或不是 object")
        else:
            mappings = identity_policy.get("runtime_kind_mappings")
            if not isinstance(mappings, list) or not mappings:
                errors.append(
                    "schema.identity_policy.runtime_kind_mappings 必须是非空 list"
                )
            else:
                seen_sections: set[str] = set()
                for index, mapping in enumerate(mappings):
                    if not isinstance(mapping, dict):
                        errors.append(f"runtime_kind_mappings[{index}] 不是 object")
                        continue
                    section = str(mapping.get("section") or "")
                    concept = str(mapping.get("class_id") or "")
                    id_field = mapping.get("id_field")
                    mapping_count += 1
                    if section not in ENTITY_SECTION_IDS:
                        errors.append(
                            f"runtime_kind_mappings[{index}] 引用未知实体 section: {section or '<empty>'}"
                        )
                    elif section in seen_sections:
                        errors.append(
                            f"runtime_kind_mappings 存在重复 section: {section}"
                        )
                    seen_sections.add(section)
                    if concept not in class_layers:
                        errors.append(
                            f"runtime_kind_mappings[{index}].class_id 引用未声明本体类: {concept or '<empty>'}"
                        )
                    if not isinstance(id_field, (str, list)) or not id_field:
                        errors.append(f"runtime_kind_mappings[{index}].id_field 缺失")
    return _check(
        "schema_reference_closure",
        "模式层引用闭包",
        errors,
        relation_count=len(relations),
        relation_ids=sorted(set(relation_ids)),
        property_count=len(property_ids),
        property_ids=sorted(set(property_ids)),
        runtime_mapping_count=mapping_count,
    )


def _build_entity_indexes(
    entities: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str], dict[str, Any]]:
    indexes: dict[str, dict[str, dict[str, Any]]] = {}
    errors: list[str] = []
    counts: dict[str, int] = {}
    if entities is None:
        return indexes, ["entities.json 未成功解析"], {"section_counts": counts}
    global_ids: dict[str, str] = {}
    for section, id_field in ENTITY_SECTION_IDS.items():
        records = entities.get(section)
        if not isinstance(records, list):
            errors.append(f"entities.{section} 缺失或不是 list")
            records = []
        section_index: dict[str, dict[str, Any]] = {}
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                errors.append(f"entities.{section}[{index}] 不是 object")
                continue
            entity_id = str(record.get(id_field) or "")
            if not entity_id:
                errors.append(f"entities.{section}[{index}].{id_field} 缺失")
                continue
            if entity_id in section_index:
                errors.append(f"entities.{section} 中存在重复 ID: {entity_id}")
            if entity_id in global_ids:
                errors.append(
                    f"静态实体 ID {entity_id} 同时出现在 {global_ids[entity_id]} 和 {section}"
                )
            section_index[entity_id] = record
            global_ids[entity_id] = section
        indexes[section] = section_index
        counts[section] = len(section_index)
    transform_edges = entities.get("transform_edges")
    if not isinstance(transform_edges, dict):
        errors.append("entities.transform_edges 缺失或不是 object")
    return (
        indexes,
        errors,
        {"section_counts": counts, "global_id_count": len(global_ids)},
    )


def _validate_entity_structure(
    entities: dict[str, Any] | None,
    release: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, dict[str, dict[str, Any]]]]:
    indexes, errors, details = _build_entity_indexes(entities)
    errors.extend(_metadata_errors(entities, filename="entities.json", release=release))
    if entities is not None:
        metadata = entities.get("metadata")
        expected_hash = (
            metadata.get("content_hash") if isinstance(metadata, dict) else None
        )
        actual_hash = _embedded_entity_hash(entities)
        details["embedded_content_hash"] = {
            "expected": expected_hash,
            "actual": actual_hash,
        }
        if expected_hash != actual_hash:
            errors.append(
                f"entities.metadata.content_hash 不匹配: expected={expected_hash}, actual={actual_hash}"
            )
    return (
        _check("entity_structure", "实体包基础结构与唯一标识", errors, **details),
        indexes,
    )


def _iter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _validate_entity_references(
    entities: dict[str, Any] | None,
    indexes: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    errors: list[str] = []
    checked = 0

    def ref(where: str, section: str, value: Any, *, optional: bool = False) -> None:
        nonlocal checked
        if value is None or value == "":
            if not optional:
                errors.append(f"{where} 缺少必要引用")
            return
        checked += 1
        if str(value) not in indexes.get(section, {}):
            errors.append(f"{where} 引用不存在的 {section} ID: {value}")

    if entities is None:
        errors.append("entities.json 未成功解析")
    else:
        for task_id, task in indexes.get("tasks", {}).items():
            metadata = (
                task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
            )
            for value in _iter_values(metadata.get("input_data_types")):
                ref(f"tasks[{task_id}].metadata.input_data_types", "data_types", value)
            ref(
                f"tasks[{task_id}].metadata.output_data_type",
                "data_types",
                metadata.get("output_data_type"),
            )

        for profile_id, profile in indexes.get("scenario_profiles", {}).items():
            metadata = (
                profile.get("metadata")
                if isinstance(profile.get("metadata"), dict)
                else {}
            )
            for value in _iter_values(profile.get("activated_tasks")):
                ref(f"scenario_profiles[{profile_id}].activated_tasks", "tasks", value)
            ref(
                f"scenario_profiles[{profile_id}].metadata.default_task_bundle_id",
                "task_bundles",
                metadata.get("default_task_bundle_id"),
            )
            for value in _iter_values(metadata.get("output_requirement_ids")):
                ref(
                    f"scenario_profiles[{profile_id}].metadata.output_requirement_ids",
                    "output_requirements",
                    value,
                )
            ref(
                f"scenario_profiles[{profile_id}].qos_policy_id",
                "qos_policies",
                profile.get("qos_policy_id"),
            )

        for contract_id, contract in indexes.get("product_contracts", {}).items():
            for value in _iter_values(contract.get("component_contract_ids")):
                ref(
                    f"product_contracts[{contract_id}].component_contract_ids",
                    "product_contracts",
                    value,
                )
            for value in _iter_values(contract.get("output_requirement_ids")):
                ref(
                    f"product_contracts[{contract_id}].output_requirement_ids",
                    "output_requirements",
                    value,
                )
            for value in _iter_values(contract.get("qos_policy_ids")):
                ref(
                    f"product_contracts[{contract_id}].qos_policy_ids",
                    "qos_policies",
                    value,
                )
            for value in _iter_values(contract.get("repair_strategy_ids")):
                ref(
                    f"product_contracts[{contract_id}].repair_strategy_ids",
                    "repair_strategies",
                    value,
                )
            for value in _iter_values(contract.get("scenario_profile_ids")):
                ref(
                    f"product_contracts[{contract_id}].scenario_profile_ids",
                    "scenario_profiles",
                    value,
                )
            for value in _iter_values(contract.get("task_bundle_ids")):
                ref(
                    f"product_contracts[{contract_id}].task_bundle_ids",
                    "task_bundles",
                    value,
                )
            for value in _iter_values(contract.get("task_ids")):
                ref(f"product_contracts[{contract_id}].task_ids", "tasks", value)
            layer_requirements = contract.get("layer_requirements")
            if not isinstance(layer_requirements, list) or not layer_requirements:
                errors.append(
                    f"product_contracts[{contract_id}].layer_requirements 必须是非空 list"
                )
            else:
                for index, layer in enumerate(layer_requirements):
                    if not isinstance(layer, dict):
                        errors.append(
                            f"product_contracts[{contract_id}].layer_requirements[{index}] 不是 object"
                        )
                        continue
                    ref(
                        f"product_contracts[{contract_id}].layer_requirements[{index}].output_requirement_id",
                        "output_requirements",
                        layer.get("output_requirement_id"),
                    )
            for required_field in (
                "evidence_requirements",
                "quality_gates",
                "repair_strategy_ids",
            ):
                if not isinstance(
                    contract.get(required_field), list
                ) or not contract.get(required_field):
                    errors.append(
                        f"product_contracts[{contract_id}].{required_field} 必须是非空 list"
                    )
            gap_policy = contract.get("gap_declaration_policy")
            if not isinstance(gap_policy, dict) or not gap_policy.get("gap_types"):
                errors.append(
                    f"product_contracts[{contract_id}].gap_declaration_policy 缺少 gap_types"
                )

        for bundle_id, bundle in indexes.get("task_bundles", {}).items():
            metadata = (
                bundle.get("metadata")
                if isinstance(bundle.get("metadata"), dict)
                else {}
            )
            for value in _iter_values(bundle.get("data_need_ids")):
                ref(f"task_bundles[{bundle_id}].data_need_ids", "data_needs", value)
            ref(
                f"task_bundles[{bundle_id}].output_requirement_id",
                "output_requirements",
                bundle.get("output_requirement_id"),
                optional=True,
            )
            ref(
                f"task_bundles[{bundle_id}].qos_policy_id",
                "qos_policies",
                bundle.get("qos_policy_id"),
            )
            for value in _iter_values(bundle.get("repair_strategy_ids")):
                ref(
                    f"task_bundles[{bundle_id}].repair_strategy_ids",
                    "repair_strategies",
                    value,
                )
            for value in _iter_values(bundle.get("requested_tasks")):
                ref(f"task_bundles[{bundle_id}].requested_tasks", "tasks", value)
            ref(
                f"task_bundles[{bundle_id}].metadata.scenario_profile_id",
                "scenario_profiles",
                metadata.get("scenario_profile_id"),
                optional=not bool(bundle.get("requires_disaster_profile")),
            )
            for value in _iter_values(metadata.get("output_requirement_ids")):
                ref(
                    f"task_bundles[{bundle_id}].metadata.output_requirement_ids",
                    "output_requirements",
                    value,
                )
            ref(
                f"task_bundles[{bundle_id}].metadata.supersedes_bundle_id",
                "task_bundles",
                metadata.get("supersedes_bundle_id"),
                optional=True,
            )

        for requirement_id, requirement in indexes.get(
            "output_requirements", {}
        ).items():
            ref(
                f"output_requirements[{requirement_id}].output_type",
                "data_types",
                requirement.get("output_type"),
            )
            ref(
                f"output_requirements[{requirement_id}].schema_policy_id",
                "output_schema_policies",
                requirement.get("schema_policy_id"),
            )

        for need_id, need in indexes.get("data_needs", {}).items():
            ref(
                f"data_needs[{need_id}].data_type_id",
                "data_types",
                need.get("data_type_id"),
            )
            ref(f"data_needs[{need_id}].task_id", "tasks", need.get("task_id"))

        for strategy_id, strategy in indexes.get("repair_strategies", {}).items():
            for value in _iter_values(strategy.get("applies_to_task_ids")):
                ref(
                    f"repair_strategies[{strategy_id}].applies_to_task_ids",
                    "tasks",
                    value,
                )
            ref(
                f"repair_strategies[{strategy_id}].from_algorithm_id",
                "algorithms",
                strategy.get("from_algorithm_id"),
                optional=True,
            )
            ref(
                f"repair_strategies[{strategy_id}].to_algorithm_id",
                "algorithms",
                strategy.get("to_algorithm_id"),
                optional=True,
            )

        for algorithm_id, algorithm in indexes.get("algorithms", {}).items():
            for value in _iter_values(algorithm.get("input_types")):
                ref(f"algorithms[{algorithm_id}].input_types", "data_types", value)
            ref(
                f"algorithms[{algorithm_id}].output_type",
                "data_types",
                algorithm.get("output_type"),
            )
            for value in _iter_values(algorithm.get("alternatives")):
                ref(f"algorithms[{algorithm_id}].alternatives", "algorithms", value)

        for spec_id, spec in indexes.get("parameter_specs", {}).items():
            ref(
                f"parameter_specs[{spec_id}].algo_id", "algorithms", spec.get("algo_id")
            )

        transform_edges = entities.get("transform_edges")
        if isinstance(transform_edges, dict):
            for source_type, targets in transform_edges.items():
                ref(f"transform_edges[{source_type}].from", "data_types", source_type)
                if not isinstance(targets, list):
                    errors.append(f"transform_edges[{source_type}] 必须是 list")
                    continue
                for target_type in targets:
                    ref(f"transform_edges[{source_type}].to", "data_types", target_type)

        for pattern_id, pattern in indexes.get("workflow_patterns", {}).items():
            steps = pattern.get("steps")
            if not isinstance(steps, list) or not steps:
                errors.append(f"workflow_patterns[{pattern_id}].steps 必须是非空 list")
                continue
            for index, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(
                        f"workflow_patterns[{pattern_id}].steps[{index}] 不是 object"
                    )
                    continue
                prefix = f"workflow_patterns[{pattern_id}].steps[{index}]"
                ref(f"{prefix}.algorithm_id", "algorithms", step.get("algorithm_id"))
                ref(
                    f"{prefix}.data_source_id",
                    "data_sources",
                    step.get("data_source_id"),
                )
                ref(
                    f"{prefix}.input_data_type",
                    "data_types",
                    step.get("input_data_type"),
                )
                ref(
                    f"{prefix}.output_data_type",
                    "data_types",
                    step.get("output_data_type"),
                )

        for source_id, source in indexes.get("data_sources", {}).items():
            for value in _iter_values(source.get("supported_types")):
                ref(f"data_sources[{source_id}].supported_types", "data_types", value)
            metadata = (
                source.get("metadata")
                if isinstance(source.get("metadata"), dict)
                else {}
            )
            for field in (
                "component_source_ids",
                "track_b_current_catalog_source_ids",
                "track_b_manual_preload_source_ids",
                "track_b_official_remote_source_ids",
                "track_b_reservation_only_source_ids",
            ):
                for value in _iter_values(metadata.get(field)):
                    ref(
                        f"data_sources[{source_id}].metadata.{field}",
                        "data_sources",
                        value,
                    )

        for policy_id, policy in indexes.get("output_schema_policies", {}).items():
            ref(
                f"output_schema_policies[{policy_id}].output_type",
                "data_types",
                policy.get("output_type"),
            )

    return _check(
        "entity_reference_closure",
        "静态实体引用闭包",
        errors,
        checked_reference_count=checked,
    )


def _validate_policy_references(
    policies: dict[str, Any] | None,
    release: dict[str, Any] | None,
    indexes: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    errors = _metadata_errors(policies, filename="policies.json", release=release)
    checked = 0

    def ref(where: str, section: str, value: Any, *, optional: bool = False) -> None:
        nonlocal checked
        if value is None or value == "":
            if not optional:
                errors.append(f"{where} 缺少必要引用")
            return
        checked += 1
        if str(value) not in indexes.get(section, {}):
            errors.append(f"{where} 引用不存在的 {section} ID: {value}")

    if policies is None:
        errors.append("policies.json 未成功解析")
    else:
        for section in sorted(POLICY_LIST_SECTIONS):
            if not isinstance(policies.get(section), list):
                errors.append(f"policies.{section} 缺失或不是 list")
        for section in sorted(POLICY_OBJECT_SECTIONS):
            if not isinstance(policies.get(section), dict):
                errors.append(f"policies.{section} 缺失或不是 object")
        if not isinstance(policies.get("rescue_organization_terms"), list):
            errors.append("policies.rescue_organization_terms 缺失或不是 list")

        task_semantics = (
            policies.get("task_semantics")
            if isinstance(policies.get("task_semantics"), list)
            else []
        )
        task_kinds: set[str] = set()
        for index, item in enumerate(task_semantics):
            if not isinstance(item, dict):
                errors.append(f"policies.task_semantics[{index}] 不是 object")
                continue
            task_kind = str(item.get("task_kind") or "")
            if not task_kind:
                errors.append(f"policies.task_semantics[{index}].task_kind 缺失")
            elif task_kind in task_kinds:
                errors.append(
                    f"policies.task_semantics 存在重复 task_kind: {task_kind}"
                )
            task_kinds.add(task_kind)
            ref(
                f"policies.task_semantics[{task_kind}].task_id",
                "tasks",
                item.get("task_id"),
            )
            ref(
                f"policies.task_semantics[{task_kind}].output_data_type",
                "data_types",
                item.get("output_data_type"),
            )
            ref(
                f"policies.task_semantics[{task_kind}].preferred_pattern_id",
                "workflow_patterns",
                item.get("preferred_pattern_id"),
                optional=True,
            )

        mission_policy = policies.get("mission_policy")
        if isinstance(mission_policy, dict):
            default_task_kind = str(
                mission_policy.get("default_direct_task_kind") or ""
            )
            checked += 1
            if default_task_kind not in task_kinds:
                errors.append(
                    "policies.mission_policy.default_direct_task_kind "
                    f"引用不存在的 task_kind: {default_task_kind or '<empty>'}"
                )

        for index, item in enumerate(policies.get("disaster_vocabulary") or []):
            if not isinstance(item, dict):
                errors.append(f"policies.disaster_vocabulary[{index}] 不是 object")
                continue
            disaster_type = str(item.get("disaster_type") or index)
            ref(
                f"policies.disaster_vocabulary[{disaster_type}].scenario_profile_id",
                "scenario_profiles",
                item.get("scenario_profile_id"),
            )
            ref(
                f"policies.disaster_vocabulary[{disaster_type}].default_task_bundle_id",
                "task_bundles",
                item.get("default_task_bundle_id"),
            )
        for index, item in enumerate(policies.get("output_contracts") or []):
            if not isinstance(item, dict):
                errors.append(f"policies.output_contracts[{index}] 不是 object")
                continue
            contract_id = str(item.get("contract_id") or index)
            ref(
                f"policies.output_contracts[{contract_id}].product_contract_id",
                "product_contracts",
                item.get("product_contract_id"),
            )
            task_kind = str(item.get("task_kind") or "")
            checked += 1
            if task_kind not in task_kinds:
                errors.append(
                    f"policies.output_contracts[{contract_id}].task_kind 不存在: {task_kind or '<empty>'}"
                )

        output_contract_ids = {
            str(item.get("contract_id"))
            for item in policies.get("output_contracts") or []
            if isinstance(item, dict) and item.get("contract_id")
        }
        for policy_id, policy in indexes.get("output_schema_policies", {}).items():
            metadata = (
                policy.get("metadata")
                if isinstance(policy.get("metadata"), dict)
                else {}
            )
            quality_contract_id = metadata.get("quality_contract_id")
            if quality_contract_id:
                checked += 1
                if str(quality_contract_id) not in output_contract_ids:
                    errors.append(
                        f"output_schema_policies[{policy_id}].metadata.quality_contract_id "
                        f"引用不存在的 policies.output_contracts ID: {quality_contract_id}"
                    )

        for section in ("quality_policies", "source_role_policies"):
            for index, item in enumerate(policies.get(section) or []):
                if not isinstance(item, dict):
                    errors.append(f"policies.{section}[{index}] 不是 object")
                    continue
                task_kind = str(item.get("task_kind") or "")
                checked += 1
                if task_kind not in task_kinds:
                    errors.append(
                        f"policies.{section}[{index}].task_kind 不存在: {task_kind or '<empty>'}"
                    )
                if section == "source_role_policies":
                    candidates = item.get("candidates")
                    if not isinstance(candidates, list) or not candidates:
                        errors.append(
                            f"policies.source_role_policies[{index}].candidates 必须是非空 list"
                        )
                    else:
                        for candidate_index, candidate in enumerate(candidates):
                            if not isinstance(candidate, dict):
                                errors.append(
                                    f"policies.source_role_policies[{index}].candidates[{candidate_index}] 不是 object"
                                )
                                continue
                            ref(
                                f"policies.source_role_policies[{index}].candidates[{candidate_index}].source_id",
                                "data_sources",
                                candidate.get("source_id"),
                            )

        quality_templates = policies.get("quality_check_templates")
        if isinstance(quality_templates, dict):
            if not isinstance(
                quality_templates.get("common"), list
            ) or not quality_templates.get("common"):
                errors.append("policies.quality_check_templates.common 必须是非空 list")
            for index, item in enumerate(policies.get("quality_policies") or []):
                if not isinstance(item, dict):
                    continue
                topology = str(item.get("topology") or "")
                checked += 1
                if topology not in quality_templates or not isinstance(
                    quality_templates.get(topology), list
                ):
                    errors.append(
                        f"policies.quality_policies[{index}].topology 引用不存在的质量模板: {topology or '<empty>'}"
                    )

        for index, item in enumerate(policies.get("source_bundle_policies") or []):
            if not isinstance(item, dict):
                errors.append(f"policies.source_bundle_policies[{index}] 不是 object")
                continue
            source_id = item.get("source_id")
            ref(
                f"policies.source_bundle_policies[{index}].source_id",
                "data_sources",
                source_id,
            )
            for field in (
                "component_candidates",
                "required_full_closure",
                "fallback_source_ids",
            ):
                values = item.get(field)
                if not isinstance(values, list):
                    errors.append(
                        f"policies.source_bundle_policies[{source_id}].{field} 必须是 list"
                    )
                    continue
                for value in values:
                    ref(
                        f"policies.source_bundle_policies[{source_id}].{field}",
                        "data_sources",
                        value,
                    )
            source_record = indexes.get("data_sources", {}).get(str(source_id))
            source_types = {
                str(value) for value in _iter_values((source_record or {}).get("supported_types"))
            }
            for fallback_source_id in item.get("fallback_source_ids") or []:
                fallback_record = indexes.get("data_sources", {}).get(str(fallback_source_id))
                fallback_types = {
                    str(value) for value in _iter_values((fallback_record or {}).get("supported_types"))
                }
                checked += 1
                if source_record is not None and fallback_record is not None and source_types != fallback_types:
                    errors.append(
                        f"policies.source_bundle_policies[{source_id}].fallback_source_ids "
                        f"I/O 类型不闭合: {source_id}={sorted(source_types)}, "
                        f"{fallback_source_id}={sorted(fallback_types)}"
                    )

        runtime_bindings = policies.get("source_runtime_bindings")
        if not isinstance(runtime_bindings, dict):
            errors.append("policies.source_runtime_bindings 缺失或不是 object")
        else:
            aliases = runtime_bindings.get("aliases")
            source_id_aliases = runtime_bindings.get("source_id_aliases")
            priority_orders = runtime_bindings.get("priority_orders")
            if not isinstance(aliases, dict) or not aliases:
                errors.append("policies.source_runtime_bindings.aliases 必须是非空 object")
                aliases = {}
            for source_id, alias in aliases.items():
                ref(
                    f"policies.source_runtime_bindings.aliases[{source_id}]",
                    "data_sources",
                    source_id,
                )
                if not str(alias or "").strip():
                    errors.append(
                        f"policies.source_runtime_bindings.aliases[{source_id}] 不能为空"
                    )
            if not isinstance(source_id_aliases, dict):
                errors.append("policies.source_runtime_bindings.source_id_aliases 必须是 object")
            else:
                for alias_id, canonical_id in source_id_aliases.items():
                    if not str(alias_id or "").strip():
                        errors.append(
                            "policies.source_runtime_bindings.source_id_aliases 含空 alias ID"
                        )
                    ref(
                        f"policies.source_runtime_bindings.source_id_aliases[{alias_id}]",
                        "data_sources",
                        canonical_id,
                    )
            if not isinstance(priority_orders, dict) or not priority_orders:
                errors.append("policies.source_runtime_bindings.priority_orders 必须是非空 object")
            else:
                for binding_id, source_ids in priority_orders.items():
                    if not isinstance(source_ids, list) or not source_ids:
                        errors.append(
                            f"policies.source_runtime_bindings.priority_orders[{binding_id}] 必须是非空 list"
                        )
                        continue
                    for source_id in source_ids:
                        ref(
                            f"policies.source_runtime_bindings.priority_orders[{binding_id}]",
                            "data_sources",
                            source_id,
                        )
                        checked += 1
                        if source_id not in aliases and binding_id != "building_height_raster":
                            errors.append(
                                f"policies.source_runtime_bindings.priority_orders[{binding_id}] "
                                f"引用无 runtime alias 的 source_id: {source_id}"
                            )
            vector_sources = runtime_bindings.get("vector_sources")
            if not isinstance(vector_sources, list) or not vector_sources:
                errors.append("policies.source_runtime_bindings.vector_sources 必须是非空 list")
            else:
                allowed_handlers = {
                    "geofabrik",
                    "gns",
                    "google_open_buildings",
                    "google_places",
                    "hydrolakes",
                    "hydrorivers",
                    "microsoft_global_buildings",
                    "overturemaps",
                }
                seen_vector_sources: set[str] = set()
                for index, binding in enumerate(vector_sources):
                    if not isinstance(binding, dict):
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources[{index}] 不是 object"
                        )
                        continue
                    source_id = str(binding.get("source_id") or "")
                    ref(
                        f"policies.source_runtime_bindings.vector_sources[{index}].source_id",
                        "data_sources",
                        source_id,
                    )
                    if source_id in seen_vector_sources:
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources source_id 重复: {source_id}"
                        )
                    seen_vector_sources.add(source_id)
                    source_record = indexes.get("data_sources", {}).get(source_id) or {}
                    source_metadata = source_record.get("metadata")
                    if not isinstance(source_metadata, dict) or source_metadata.get("kind") != "raw_vector":
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources[{source_id}] "
                            "必须引用 kind=raw_vector 的 DataSource"
                        )
                    local_candidates = binding.get("local_candidates")
                    if not isinstance(local_candidates, list):
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources[{source_id}].local_candidates "
                            "必须是 list"
                        )
                        local_candidates = []
                    elif any(
                        not isinstance(candidate, list)
                        or not candidate
                        or any(not str(part or "").strip() for part in candidate)
                        for candidate in local_candidates
                    ):
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources[{source_id}].local_candidates "
                            "含无效路径"
                        )
                    handler = binding.get("remote_handler")
                    if handler is not None and str(handler) not in allowed_handlers:
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources[{source_id}].remote_handler "
                            f"不受支持: {handler}"
                        )
                    if handler == "geofabrik" and not str(binding.get("remote_layer_name") or "").strip():
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources[{source_id}].remote_layer_name "
                            "在 geofabrik handler 下不能为空"
                        )
                    if not local_candidates and handler is None:
                        errors.append(
                            f"policies.source_runtime_bindings.vector_sources[{source_id}] "
                            "既无本地候选也无远程 handler"
                        )
            raster_sources = runtime_bindings.get("raster_sources")
            if not isinstance(raster_sources, list) or not raster_sources:
                errors.append("policies.source_runtime_bindings.raster_sources 必须是非空 list")
            else:
                for index, binding in enumerate(raster_sources):
                    if not isinstance(binding, dict):
                        errors.append(
                            f"policies.source_runtime_bindings.raster_sources[{index}] 不是 object"
                        )
                        continue
                    ref(
                        f"policies.source_runtime_bindings.raster_sources[{index}].source_id",
                        "data_sources",
                        binding.get("source_id"),
                    )
                    if not isinstance(binding.get("file_patterns"), list) or not binding.get("file_patterns"):
                        errors.append(
                            f"policies.source_runtime_bindings.raster_sources[{index}].file_patterns 必须是非空 list"
                        )
                    local_candidates = binding.get("local_candidates")
                    if not isinstance(local_candidates, list) or not local_candidates:
                        errors.append(
                            f"policies.source_runtime_bindings.raster_sources[{index}].local_candidates 必须是非空 list"
                        )
                    elif any(
                        not isinstance(candidate, list) or not candidate
                        for candidate in local_candidates
                    ):
                        errors.append(
                            f"policies.source_runtime_bindings.raster_sources[{index}].local_candidates 含无效路径"
                        )

        for index, item in enumerate(policies.get("quality_component_policies") or []):
            if not isinstance(item, dict):
                errors.append(f"policies.quality_component_policies[{index}] 不是 object")
                continue
            task_kind = str(item.get("task_kind") or "")
            checked += 1
            if task_kind not in task_kinds:
                errors.append(
                    f"policies.quality_component_policies[{index}].task_kind 不存在: {task_kind or '<empty>'}"
                )
            for field in ("expected_source_ids", "external_optional_source_ids"):
                source_ids = item.get(field)
                if not isinstance(source_ids, list):
                    errors.append(
                        f"policies.quality_component_policies[{task_kind}].{field} 必须是 list"
                    )
                    continue
                if field == "expected_source_ids" and not source_ids:
                    errors.append(
                        f"policies.quality_component_policies[{task_kind}].expected_source_ids 不能为空"
                    )
                for source_id in source_ids:
                    ref(
                        f"policies.quality_component_policies[{task_kind}].{field}",
                        "data_sources",
                        source_id,
                    )

        artifact_evaluation = policies.get("artifact_evaluation_policy")
        if not isinstance(artifact_evaluation, dict):
            errors.append("policies.artifact_evaluation_policy 缺失或不是 object")
        else:
            for field in ("sliver_area_threshold_sq_m", "metadata_only_threshold_bytes"):
                checked += 1
                value = artifact_evaluation.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    errors.append(
                        f"policies.artifact_evaluation_policy.{field} 必须是正数"
                    )
            supported_extensions = artifact_evaluation.get("supported_vector_extensions")
            if not isinstance(supported_extensions, list) or not supported_extensions:
                errors.append(
                    "policies.artifact_evaluation_policy.supported_vector_extensions 必须是非空 list"
                )
                supported_extensions = []
            elif any(
                not str(extension or "").startswith(".")
                for extension in supported_extensions
            ):
                errors.append(
                    "policies.artifact_evaluation_policy.supported_vector_extensions 必须使用点号扩展名"
                )
            large_artifact_mode = artifact_evaluation.get("large_artifact_mode")
            if large_artifact_mode not in {"metadata_only", "sample"}:
                errors.append(
                    "policies.artifact_evaluation_policy.large_artifact_mode 必须为 metadata_only 或 sample"
                )
            sampling_policy = artifact_evaluation.get("sampling_policy")
            if not isinstance(sampling_policy, dict):
                errors.append(
                    "policies.artifact_evaluation_policy.sampling_policy 必须是 object"
                )
            elif large_artifact_mode == "sample":
                if sampling_policy.get("authorized") is not True:
                    errors.append(
                        "large_artifact_mode=sample 时 sampling_policy.authorized 必须为 true"
                    )
                if sampling_policy.get("strategy") != "head":
                    errors.append(
                        "large_artifact_mode=sample 时 sampling_policy.strategy 必须为 head"
                    )
                max_features = sampling_policy.get("max_features")
                if isinstance(max_features, bool) or not isinstance(max_features, int) or max_features <= 0:
                    errors.append(
                        "large_artifact_mode=sample 时 sampling_policy.max_features 必须是正整数"
                    )
                sample_extensions = sampling_policy.get("applicable_extensions")
                if not isinstance(sample_extensions, list) or not sample_extensions:
                    errors.append(
                        "large_artifact_mode=sample 时 sampling_policy.applicable_extensions 必须是非空 list"
                    )
                elif any(extension not in supported_extensions for extension in sample_extensions):
                    errors.append(
                        "sampling_policy.applicable_extensions 必须是 supported_vector_extensions 的子集"
                    )

        fault_policy = policies.get("fault_policy")
        if not isinstance(fault_policy, dict):
            errors.append("policies.fault_policy 缺失或不是 object")
        else:
            classification = fault_policy.get("classification")
            known_failure_classes: set[str] = set()
            required_scopes = {
                "general",
                "source_asset",
                "source_acquisition",
                "scenario_child",
            }
            if not isinstance(classification, dict):
                errors.append("policies.fault_policy.classification 缺失或不是 object")
            else:
                if not str(classification.get("policy_id") or "").strip():
                    errors.append("policies.fault_policy.classification.policy_id 不能为空")
                for section in ("default_by_scope", "empty_by_scope"):
                    defaults = classification.get(section)
                    if not isinstance(defaults, dict):
                        errors.append(
                            f"policies.fault_policy.classification.{section} 必须是 object"
                        )
                        continue
                    missing_scopes = sorted(required_scopes - set(defaults))
                    if missing_scopes:
                        errors.append(
                            f"policies.fault_policy.classification.{section} 缺少 scope: "
                            + ", ".join(missing_scopes)
                        )
                    for scope, failure_class in defaults.items():
                        if scope not in required_scopes:
                            errors.append(
                                f"policies.fault_policy.classification.{section} 含未知 scope: {scope}"
                            )
                        if not isinstance(failure_class, str):
                            errors.append(
                                f"policies.fault_policy.classification.{section}.{scope} 必须是 string"
                            )
                        elif failure_class:
                            known_failure_classes.add(failure_class)

                rules = classification.get("rules")
                if not isinstance(rules, list) or not rules:
                    errors.append(
                        "policies.fault_policy.classification.rules 必须是非空 list"
                    )
                    rules = []
                seen_priorities: set[int] = set()
                for index, rule in enumerate(rules):
                    prefix = f"policies.fault_policy.classification.rules[{index}]"
                    if not isinstance(rule, dict):
                        errors.append(f"{prefix} 不是 object")
                        continue
                    priority = rule.get("priority")
                    if (
                        isinstance(priority, bool)
                        or not isinstance(priority, int)
                        or priority <= 0
                    ):
                        errors.append(f"{prefix}.priority 必须是正整数")
                    elif priority in seen_priorities:
                        errors.append(f"{prefix}.priority 重复: {priority}")
                    else:
                        seen_priorities.add(priority)
                    failure_class = str(rule.get("failure_class") or "").strip()
                    if not failure_class:
                        errors.append(f"{prefix}.failure_class 不能为空")
                    else:
                        known_failure_classes.add(failure_class)
                    scopes = rule.get("scopes")
                    if not isinstance(scopes, list) or not scopes:
                        errors.append(f"{prefix}.scopes 必须是非空 list")
                    else:
                        invalid_scopes = sorted(
                            {
                                str(scope)
                                for scope in scopes
                                if str(scope) not in required_scopes | {"*"}
                            }
                        )
                        if invalid_scopes:
                            errors.append(
                                f"{prefix}.scopes 含未知 scope: {', '.join(invalid_scopes)}"
                            )

                    has_matcher = False
                    for field in ("match_any", "exception_types"):
                        matcher = rule.get(field)
                        if matcher is None:
                            continue
                        if (
                            not isinstance(matcher, list)
                            or not matcher
                            or any(not str(value).strip() for value in matcher)
                        ):
                            errors.append(f"{prefix}.{field} 必须是非空字符串 list")
                        else:
                            has_matcher = True
                    alternatives = rule.get("match_all_alternatives")
                    if alternatives is not None:
                        if not isinstance(alternatives, list) or not alternatives:
                            errors.append(
                                f"{prefix}.match_all_alternatives 必须是非空 list"
                            )
                        elif any(
                            not isinstance(alternative, list)
                            or not alternative
                            or any(not str(value).strip() for value in alternative)
                            for alternative in alternatives
                        ):
                            errors.append(
                                f"{prefix}.match_all_alternatives 必须由非空字符串 list 组成"
                            )
                        else:
                            has_matcher = True
                    if not has_matcher:
                        errors.append(f"{prefix} 至少需要一个有效匹配器")

            fallback_faults = fault_policy.get("source_candidate_fallback_faults")
            if not isinstance(fallback_faults, list) or not fallback_faults:
                errors.append(
                    "policies.fault_policy.source_candidate_fallback_faults 必须是非空 list"
                )
            else:
                for failure_class in fallback_faults:
                    checked += 1
                    normalized = str(failure_class or "").strip()
                    if not normalized:
                        errors.append(
                            "policies.fault_policy.source_candidate_fallback_faults 不能含空值"
                        )
                    elif normalized not in known_failure_classes:
                        errors.append(
                            "policies.fault_policy.source_candidate_fallback_faults "
                            f"引用未声明分类: {normalized}"
                        )

            source_attempt_statuses = {
                str(value).strip()
                for value in fault_policy.get("source_attempt_statuses") or []
                if str(value).strip()
            }
            default_empty_status = str(
                fault_policy.get("default_empty_coverage_status") or ""
            ).strip()
            if not default_empty_status:
                errors.append(
                    "policies.fault_policy.default_empty_coverage_status 不能为空"
                )
            elif default_empty_status not in source_attempt_statuses:
                errors.append(
                    "policies.fault_policy.default_empty_coverage_status "
                    f"引用未声明状态: {default_empty_status}"
                )
            empty_status_overrides = fault_policy.get(
                "empty_coverage_status_by_source"
            )
            if not isinstance(empty_status_overrides, dict):
                errors.append(
                    "policies.fault_policy.empty_coverage_status_by_source 必须是 object"
                )
            else:
                for source_id, status in empty_status_overrides.items():
                    ref(
                        "policies.fault_policy.empty_coverage_status_by_source",
                        "data_sources",
                        source_id,
                    )
                    checked += 1
                    if str(status or "").strip() not in source_attempt_statuses:
                        errors.append(
                            "policies.fault_policy.empty_coverage_status_by_source "
                            f"引用未声明状态: {status}"
                        )

            inferred_faults = fault_policy.get("inferred_missing_fault_by_control")
            if not isinstance(inferred_faults, dict):
                errors.append(
                    "policies.fault_policy.inferred_missing_fault_by_control 必须是 object"
                )
            else:
                for key in ("external", "internal"):
                    checked += 1
                    failure_class = str(inferred_faults.get(key) or "").strip()
                    if failure_class not in known_failure_classes:
                        errors.append(
                            "policies.fault_policy.inferred_missing_fault_by_control "
                            f"{key} 引用未声明分类: {failure_class or '<empty>'}"
                        )

            inspection_guidance = fault_policy.get("inspection_guidance")
            if not isinstance(inspection_guidance, dict):
                errors.append("policies.fault_policy.inspection_guidance 必须是 object")
            else:
                failure_actions = inspection_guidance.get("failure_actions")
                if not isinstance(failure_actions, dict) or not failure_actions:
                    errors.append(
                        "policies.fault_policy.inspection_guidance.failure_actions 必须是非空 object"
                    )
                else:
                    for failure_class, action in failure_actions.items():
                        checked += 1
                        if str(failure_class) not in known_failure_classes:
                            errors.append(
                                "policies.fault_policy.inspection_guidance.failure_actions "
                                f"引用未声明分类: {failure_class}"
                            )
                        if not str(action or "").strip():
                            errors.append(
                                "policies.fault_policy.inspection_guidance.failure_actions "
                                f"{failure_class} 的 action 不能为空"
                            )
                for section in ("recoverability_actions", "phase_actions"):
                    actions = inspection_guidance.get(section)
                    if not isinstance(actions, dict) or not actions:
                        errors.append(
                            f"policies.fault_policy.inspection_guidance.{section} 必须是非空 object"
                        )
                    elif any(
                        not str(key or "").strip() or not str(value or "").strip()
                        for key, value in actions.items()
                    ):
                        errors.append(
                            f"policies.fault_policy.inspection_guidance.{section} "
                            "不能含空 key/action"
                        )

        recovery = policies.get("recovery_policy")
        if not isinstance(recovery, dict):
            errors.append("policies.recovery_policy 缺失或不是 object")
        else:
            strategy_ids = recovery.get("authorized_strategy_ids")
            if not isinstance(strategy_ids, list) or not strategy_ids:
                errors.append(
                    "policies.recovery_policy.authorized_strategy_ids 必须是非空 list"
                )
            else:
                for strategy_id in strategy_ids:
                    ref(
                        "policies.recovery_policy.authorized_strategy_ids",
                        "repair_strategies",
                        strategy_id,
                    )
            artifact_strategy_order = recovery.get("artifact_strategy_order")
            if not isinstance(artifact_strategy_order, list) or not artifact_strategy_order:
                errors.append(
                    "policies.recovery_policy.artifact_strategy_order 必须是非空 list"
                )
            else:
                seen_orders: set[int] = set()
                for index, item in enumerate(artifact_strategy_order):
                    if not isinstance(item, dict):
                        errors.append(
                            f"policies.recovery_policy.artifact_strategy_order[{index}] 不是 object"
                        )
                        continue
                    ref(
                        f"policies.recovery_policy.artifact_strategy_order[{index}].strategy_id",
                        "repair_strategies",
                        item.get("strategy_id"),
                    )
                    order = item.get("order")
                    if isinstance(order, bool) or not isinstance(order, int) or order <= 0:
                        errors.append(
                            f"policies.recovery_policy.artifact_strategy_order[{index}].order 必须是正整数"
                        )
                    elif order in seen_orders:
                        errors.append(
                            f"policies.recovery_policy.artifact_strategy_order.order 重复: {order}"
                        )
                    else:
                        seen_orders.add(order)
                    if not str(item.get("action") or "").strip():
                        errors.append(
                            f"policies.recovery_policy.artifact_strategy_order[{index}].action 不能为空"
                        )

        runtime_gates = policies.get("runtime_gates")
        if not isinstance(runtime_gates, dict):
            errors.append("policies.runtime_gates 缺失或不是 object")
        else:
            if runtime_gates.get("missing_required_knowledge") != "fail_closed":
                errors.append(
                    "policies.runtime_gates.missing_required_knowledge 必须为 fail_closed"
                )
            if runtime_gates.get("backend_fallback") != "forbidden_in_strict_mode":
                errors.append(
                    "policies.runtime_gates.backend_fallback 必须为 forbidden_in_strict_mode"
                )

    return _check(
        "policy_reference_closure",
        "策略知识引用闭包",
        errors,
        checked_reference_count=checked,
    )


def _validate_workflow_dags(
    indexes: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, Any]:
    errors: list[str] = []
    pattern_details: dict[str, Any] = {}
    algorithms = indexes.get("algorithms", {})
    patterns = indexes.get("workflow_patterns", {})
    for pattern_id, pattern in patterns.items():
        steps = pattern.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"workflow_patterns[{pattern_id}].steps 必须是非空 list")
            continue
        orders: dict[int, dict[str, Any]] = {}
        graph: dict[int, list[int]] = {}
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            order = step.get("order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 1:
                errors.append(
                    f"workflow_patterns[{pattern_id}].steps[{index}].order 必须是正整数"
                )
                continue
            if order in orders:
                errors.append(
                    f"workflow_patterns[{pattern_id}] 存在重复 step order: {order}"
                )
            orders[order] = step
            graph.setdefault(order, [])
        edge_count = 0
        for order, step in orders.items():
            dependencies = step.get("depends_on")
            if not isinstance(dependencies, list):
                errors.append(
                    f"workflow_patterns[{pattern_id}].step[{order}].depends_on 必须是 list"
                )
                continue
            for dependency in dependencies:
                if not isinstance(dependency, int) or isinstance(dependency, bool):
                    errors.append(
                        f"workflow_patterns[{pattern_id}].step[{order}] 包含非整数依赖: {dependency}"
                    )
                    continue
                if dependency not in orders:
                    errors.append(
                        f"workflow_patterns[{pattern_id}].step[{order}] 引用不存在的依赖 step: {dependency}"
                    )
                    continue
                graph.setdefault(dependency, []).append(order)
                edge_count += 1
                if dependency >= order:
                    errors.append(
                        f"workflow_patterns[{pattern_id}].step[{order}] 的依赖 {dependency} 不早于当前步骤"
                    )
            algorithm_id = str(step.get("algorithm_id") or "")
            algorithm = algorithms.get(algorithm_id)
            if algorithm is not None:
                input_type = step.get("input_data_type")
                output_type = step.get("output_data_type")
                if input_type not in _iter_values(algorithm.get("input_types")):
                    errors.append(
                        f"workflow_patterns[{pattern_id}].step[{order}] 输入 {input_type} 不在算法 {algorithm_id} 输入集合中"
                    )
                if output_type != algorithm.get("output_type"):
                    errors.append(
                        f"workflow_patterns[{pattern_id}].step[{order}] 输出 {output_type} 与算法 {algorithm_id} 输出 {algorithm.get('output_type')} 不一致"
                    )

        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(node: int) -> bool:
            if node in visiting:
                return False
            if node in visited:
                return True
            visiting.add(node)
            for child in graph.get(node, []):
                if not visit(child):
                    return False
            visiting.remove(node)
            visited.add(node)
            return True

        acyclic = all(visit(order) for order in sorted(orders))
        if not acyclic:
            errors.append(f"workflow_patterns[{pattern_id}] 包含有向环")
        pattern_details[pattern_id] = {
            "step_count": len(orders),
            "edge_count": edge_count,
            "acyclic": acyclic,
        }
    if not patterns:
        errors.append("没有可验证的 workflow pattern")
    return _check(
        "workflow_dag",
        "工作流 DAG 与算法 I/O",
        errors,
        pattern_count=len(patterns),
        patterns=pattern_details,
    )


def _validate_competency_questions(
    schema: dict[str, Any] | None, class_layers: dict[str, str]
) -> dict[str, Any]:
    errors: list[str] = []
    cq_ids: list[str] = []
    covered_layers: set[str] = set()
    if schema is None:
        errors.append("schema.json 未成功解析")
        questions: list[Any] = []
    else:
        value = schema.get("competency_questions")
        if not isinstance(value, list):
            errors.append("schema.competency_questions 缺失或不是 list")
            questions = []
        else:
            questions = value
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            errors.append(f"competency_questions[{index}] 不是 object")
            continue
        cq_id = str(question.get("id") or "")
        if not cq_id:
            errors.append(f"competency_questions[{index}].id 缺失")
        else:
            cq_ids.append(cq_id)
        if (
            not isinstance(question.get("question"), str)
            or not str(question.get("question")).strip()
        ):
            errors.append(
                f"competency_questions[{cq_id or index}].question 必须是非空字符串"
            )
        concepts = question.get("required_concepts")
        if not isinstance(concepts, list) or not concepts:
            errors.append(
                f"competency_questions[{cq_id or index}].required_concepts 必须是非空 list"
            )
            continue
        for concept in concepts:
            concept_id = str(concept)
            if concept_id not in class_layers:
                errors.append(
                    f"competency_questions[{cq_id or index}] 引用未声明本体类: {concept_id}"
                )
            else:
                covered_layers.add(class_layers[concept_id])
    duplicates = sorted({value for value in cq_ids if cq_ids.count(value) > 1})
    if duplicates:
        errors.append(f"重复 competency question ID: {', '.join(duplicates)}")
    missing = sorted(REQUIRED_CQ_IDS - set(cq_ids))
    if missing:
        errors.append(f"缺少 v1 必要 competency questions: {', '.join(missing)}")
    uncovered_layers = sorted(EXPECTED_LAYER_IDS - covered_layers)
    if uncovered_layers:
        errors.append(f"competency questions 未覆盖层级: {', '.join(uncovered_layers)}")
    return _check(
        "competency_questions",
        "能力问题完整性与概念覆盖",
        errors,
        question_ids=sorted(set(cq_ids)),
        question_count=len(questions),
        covered_layers=sorted(covered_layers),
    )


def verify_release_directory(release_dir: Path) -> dict[str, Any]:
    root = Path(release_dir).resolve()
    release, release_error = _load_json_object(root / "release.json")
    schema, schema_error = _load_json_object(root / "schema.json")
    entities, entities_error = _load_json_object(root / "entities.json")
    policies, policies_error = _load_json_object(root / "policies.json")

    checks: list[dict[str, Any]] = []
    checks.append(_validate_release_status(release, release_error))
    checks.append(_validate_file_hashes(root, release))
    parse_errors = [
        error for error in (schema_error, entities_error, policies_error) if error
    ]
    checks.append(
        _check(
            "json_documents",
            "冻结 JSON 文档可解析性",
            parse_errors,
            parsed_files={
                "schema.json": schema is not None,
                "entities.json": entities is not None,
                "policies.json": policies is not None,
            },
        )
    )
    checks.append(_validate_semantic_hash(release, schema, entities, policies))
    layer_check, class_layers = _validate_schema_layers(schema, release)
    checks.append(layer_check)
    checks.append(_validate_schema_references(schema, class_layers))
    entity_check, indexes = _validate_entity_structure(entities, release)
    checks.append(entity_check)
    checks.append(_validate_entity_references(entities, indexes))
    checks.append(_validate_policy_references(policies, release, indexes))
    checks.append(_validate_workflow_dags(indexes))
    checks.append(_validate_competency_questions(schema, class_layers))

    failed = [check["id"] for check in checks if not check["passed"]]
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "verifier_id": VERIFIER_ID,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "release_dir": str(root),
        "passed": not failed,
        "release_identity": {
            "release_id": release.get("release_id") if release else None,
            "ontology_version": release.get("ontology_version") if release else None,
            "knowledge_version": release.get("knowledge_version") if release else None,
            "semantic_hash": release.get("semantic_hash") if release else None,
        },
        "summary": {
            "check_count": len(checks),
            "passed_count": len(checks) - len(failed),
            "failed_count": len(failed),
            "failed_check_ids": failed,
        },
        "checks": checks,
    }


def _internal_error_report(release_dir: Path, exc: Exception) -> dict[str, Any]:
    check = _check("internal_error", "验证器内部错误", [f"{type(exc).__name__}: {exc}"])
    return {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "verifier_id": VERIFIER_ID,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "release_dir": str(Path(release_dir).resolve()),
        "passed": False,
        "release_identity": {},
        "summary": {
            "check_count": 1,
            "passed_count": 0,
            "failed_count": 1,
            "failed_check_ids": ["internal_error"],
        },
        "checks": [check],
    }


def _mark_report_write_failure(report: dict[str, Any], message: str) -> None:
    check = _check("report_output", "验证报告输出", [message])
    report.setdefault("checks", []).append(check)
    report["passed"] = False
    failed = [item["id"] for item in report["checks"] if not item.get("passed")]
    report["summary"] = {
        "check_count": len(report["checks"]),
        "passed_count": len(report["checks"]) - len(failed),
        "failed_count": len(failed),
        "failed_check_ids": failed,
    }


def _write_report(report: dict[str, Any], requested_path: Path) -> Path:
    requested = Path(requested_path).resolve()
    try:
        requested.parent.mkdir(parents=True, exist_ok=True)
        requested.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return requested
    except OSError as exc:
        _mark_report_write_failure(report, f"无法写入 {requested}: {exc}")
        fallback = (Path.cwd() / "verification_report.json").resolve()
        if fallback == requested:
            raise
        fallback.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return fallback


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="独立验证冻结的 FusionAgent KG 发布包。"
    )
    parser.add_argument(
        "--release-dir", default="kg/ontology/v1.0.0", help="只读 KG 发布目录"
    )
    parser.add_argument(
        "--report-path",
        default="verification_report.json",
        help="机器可读验证报告路径（默认当前目录 verification_report.json）",
    )
    args = parser.parse_args(argv)
    release_dir = Path(args.release_dir)
    try:
        report = verify_release_directory(release_dir)
    except (
        Exception
    ) as exc:  # The verifier must still emit a report for unexpected failures.
        report = _internal_error_report(release_dir, exc)
    try:
        report_path = _write_report(report, Path(args.report_path))
    except OSError as exc:
        print(
            json.dumps(
                _internal_error_report(release_dir, exc),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "report_path": str(report_path),
                "failed_check_ids": report["summary"]["failed_check_ids"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
