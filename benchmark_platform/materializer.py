from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord
from benchmark_platform.canonical import canonical_sha256


class MemberMaterializerError(BenchmarkPlatformValidationError):
    """Raised when a template cannot produce a relation-valid member set."""


_MISSING = object()


def merge_v2_extension(base_template: Mapping[str, Any], extension_document: Mapping[str, Any]) -> dict[str, Any]:
    """Bind a task-indexed v2 envelope to its exact base template snapshot."""
    if extension_document.get("base_template_id") != base_template.get("template_family_id"):
        raise _failure("extension_identity_mismatch", "v2 extension base_template_id differs from the base template")
    expected_hash = extension_document.get("base_template_sha256")
    actual_hash = canonical_sha256(base_template)
    if expected_hash != actual_hash:
        raise _failure("extension_hash_mismatch", "v2 extension is not bound to the supplied base template hash")
    extensions = extension_document.get("v2_extensions")
    if not isinstance(extensions, Mapping):
        raise _failure("extension_invalid", "v2 extension must contain a v2_extensions object")
    merged = deepcopy(dict(base_template))
    merged["v2_extensions"] = deepcopy(dict(extensions))
    for key in ("frozen_plan_sha256", "lineage_binding"):
        if key in extension_document:
            merged[key] = deepcopy(extension_document[key])
    return merged


def _failure(code: str, message: str, path: tuple[str | int, ...] = ()) -> MemberMaterializerError:
    return MemberMaterializerError([
        FailureRecord(
            failure_class=FailureClass.RUNTIME_INVALID_STATE,
            message=message,
            path=path,
            validator="member_materializer",
            details={"code": code},
        )
    ])


def _tokens(path: str) -> tuple[str | int, ...]:
    if not isinstance(path, str) or not path.startswith("$"):
        raise _failure("invalid_path", f"materializer path must start with $: {path!r}")
    result: list[str | int] = []
    index = 1
    while index < len(path):
        if path[index] == ".":
            end = index + 1
            while end < len(path) and (path[end].isalnum() or path[end] == "_"):
                end += 1
            if end == index + 1:
                raise _failure("invalid_path", f"unsupported materializer path: {path}")
            result.append(path[index + 1:end])
            index = end
        elif path[index] == "[":
            end = path.find("]", index + 1)
            if end < 0 or not path[index + 1:end].isdigit():
                raise _failure("invalid_path", f"unsupported materializer path: {path}")
            result.append(int(path[index + 1:end]))
            index = end + 1
        else:
            raise _failure("invalid_path", f"unsupported materializer path: {path}")
    return tuple(result)


def _get(document: Mapping[str, Any], path: str) -> Any:
    current: Any = document
    for token in _tokens(path):
        if isinstance(token, str) and isinstance(current, Mapping) and token in current:
            current = current[token]
        elif isinstance(token, int) and isinstance(current, list) and token < len(current):
            current = current[token]
        else:
            return _MISSING
    return current


def _set(document: dict[str, Any], path: str, value: Any) -> None:
    tokens = _tokens(path)
    if not tokens:
        raise _failure("invalid_path", "root replacement is not supported")
    current: Any = document
    for token in tokens[:-1]:
        if isinstance(token, str) and isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(token, int) and isinstance(current, list) and token < len(current):
            current = current[token]
        else:
            raise _failure("missing_path", f"materializer path does not resolve: {path}")
    final = tokens[-1]
    if isinstance(final, str) and isinstance(current, dict) and final in current:
        current[final] = deepcopy(value)
    elif isinstance(final, int) and isinstance(current, list) and final < len(current):
        current[final] = deepcopy(value)
    else:
        raise _failure("missing_path", f"materializer path does not resolve: {path}")


def _specs(template: Mapping[str, Any], role: str) -> list[Mapping[str, Any]]:
    variables = template.get("variables")
    values = variables.get(role, []) if isinstance(variables, Mapping) else []
    if not isinstance(values, list):
        raise _failure("invalid_variable_domain", f"{role} must be a list")
    return [item for item in values if isinstance(item, Mapping)]


def _value_options(current: Any, spec: Mapping[str, Any]) -> list[Any]:
    allowed = spec.get("allowed_values", [])
    if not isinstance(allowed, list):
        raise _failure("invalid_variable_domain", "allowed_values must be a list")
    options: list[Any] = []
    for candidate in allowed:
        value = candidate
        # Order variables are authored as task IDs while their payload is a list.
        if isinstance(current, list) and isinstance(candidate, str) and candidate in current:
            value = [candidate, *[item for item in current if item != candidate]]
        if value != current and value not in options:
            options.append(deepcopy(value))
    # A single authored permutation still defines an order variable. Derive the
    # next cyclic order without inventing a new semantic value.
    if not options and isinstance(current, list) and len(current) > 1:
        options.append([*current[1:], current[0]])
    return options


def _mutated_payload(base: Mapping[str, Any], spec: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    payload = deepcopy(dict(base))
    path = spec.get("json_path")
    if not isinstance(path, str):
        raise _failure("invalid_variable_domain", "variable json_path is required")
    current = _get(payload, path)
    if current is _MISSING:
        raise _failure("missing_path", f"variable path does not resolve: {path}")
    options = _value_options(current, spec)
    if not options:
        raise _failure("no_alternative_value", f"variable has no alternative value: {spec.get('variable_id')}")
    _set(payload, path, options[ordinal % len(options)])
    return payload


def _path_is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[")


def _validate_role_separation(template: Mapping[str, Any], unit_type: str) -> None:
    causal = [str(item.get("json_path")) for item in _specs(template, "causal_variables") if isinstance(item.get("json_path"), str)]
    invariants = [str(item.get("json_path")) for item in _specs(template, "invariants") if isinstance(item.get("json_path"), str)]
    nuisance = [str(item.get("json_path")) for item in _specs(template, "nuisance_variables") if isinstance(item.get("json_path"), str)]
    if any(_path_is_under(left, right) or _path_is_under(right, left) for left in causal for right in invariants):
        raise _failure("variable_role_overlap", "causal and invariant paths overlap; relation members would be invalid")
    if unit_type == "invariant_set" and any(_path_is_under(left, right) or _path_is_under(right, left) for left in nuisance for right in invariants):
        raise _failure("variable_role_overlap", "nuisance and invariant paths overlap; invariant members cannot be materialized")


def materialize_members(template: Mapping[str, Any], member_count: int, seed: int = 0) -> tuple[dict[str, Any], ...]:
    """Materialize a deterministic relation unit from the authored variable domains.

    This function only mutates fields declared by the template. It does not add
    request/plan fields that are absent from the frozen v1 payload schema.
    """
    if member_count < 1:
        raise _failure("invalid_member_count", "member_count must be positive")
    unit = template.get("experiment_unit")
    unit_type = unit.get("unit_type") if isinstance(unit, Mapping) else None
    if unit_type not in {"single", "counterfactual_pair", "invariant_set", "composition_family", "temporal_trace"}:
        raise _failure("invalid_unit_type", "template experiment unit has an unknown unit type")
    _validate_role_separation(template, unit_type)
    base = deepcopy(dict(template))
    if unit_type == "single":
        if member_count != 1:
            raise _failure("invalid_member_count", "single units require exactly one member")
        return (base,)

    roles = "causal_variables" if unit_type in {"counterfactual_pair", "composition_family", "temporal_trace"} else "nuisance_variables"
    candidates = _specs(template, roles)
    if not candidates:
        raise _failure("missing_mutation_role", f"{unit_type} requires {roles}")
    start = abs(int(seed)) % len(candidates)
    if unit_type == "counterfactual_pair":
        spec = candidates[start]
        return (base, _mutated_payload(base, spec, 0))
    if unit_type == "invariant_set":
        return tuple(base if index == 0 else _mutated_payload(base, candidates[(start + index - 1) % len(candidates)], index - 1) for index in range(member_count))
    # Composition and temporal units vary one declared causal dimension per
    # member, keeping task sets and delivery history structurally intact.
    return tuple(base if index == 0 else _mutated_payload(base, candidates[(start + index - 1) % len(candidates)], index - 1) for index in range(member_count))
