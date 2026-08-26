from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord


DESIGN_TAG = "benchmark-design-freeze-v1"
DESIGN_COMMIT = "08b55f7e03eabb74721979153df57aeee3200538"
DESIGN_ID = "fusionagent.benchmark-design.v1"
FREEZE_ID = "fusionagent.benchmark-design-freeze.v1"
KG_RELEASE_ID = "fusionagent-kg-v1.0.0"
KG_SEMANTIC_HASH = "sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e"
PROTOCOL_MANIFEST = "docs/current/benchmark/platform/v1/protocol_manifest.json"


class DesignLoaderError(BenchmarkPlatformValidationError):
    """Raised when a frozen design binding cannot be established."""


class FrozenDesignBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    design_root: str
    design_id: str = Field(min_length=1)
    freeze_id: str = Field(min_length=1)
    design_tag: str = Field(min_length=1)
    design_commit: str = Field(min_length=40, max_length=40)
    kg_release_id: str = Field(min_length=1)
    kg_semantic_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    manifest: dict[str, Any]
    protocol_manifest: dict[str, Any]
    assets: dict[str, Any]
    schema_document: dict[str, Any]
    matrix: dict[str, Any]
    evaluation: dict[str, Any]
    selection: dict[str, Any]
    protocol_review: dict[str, Any]
    kg_release: dict[str, Any]
    kg_entities: dict[str, Any]
    kg_policies: dict[str, Any]

    @property
    def schema(self) -> dict[str, Any]:
        return self.schema_document


def _failure(code: str, message: str, path: tuple[str | int, ...] = ()) -> DesignLoaderError:
    return DesignLoaderError(
        [
            FailureRecord(
                failure_class=FailureClass.RUNTIME_INVALID_STATE,
                message=message,
                path=path,
                validator="design_loader",
                details={"code": code},
            )
        ]
    )


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise _failure("missing_reference", f"cannot load JSON asset: {path}") from error
    if not isinstance(value, dict):
        raise _failure("missing_reference", f"JSON asset must be an object: {path}")
    return value


def _sha256(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            data = handle.read().replace(b"\r\n", b"\n")
    except OSError as error:
        raise _failure("missing_reference", f"missing frozen asset: {path}") from error
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _raw_sha256(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as error:
        raise _failure("missing_reference", f"missing frozen asset: {path}") from error
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _repo_root_for(design_root: str, repo_root: str | None) -> str:
    if repo_root:
        return repo_root
    marker = "docs/current/benchmark/v1"
    normalized = design_root.replace("\\", "/").rstrip("/")
    if normalized.endswith(marker):
        return normalized[: -len(marker)].rstrip("/")
    raise _failure("missing_reference", "repo_root is required when design_root is outside the repository")


def _join(root: str, relative: str) -> str:
    return root.rstrip("\\/") + "/" + relative.replace("\\", "/")


def _git_tag_commit(repo_root: str, tag: str) -> str:
    try:
        subprocess = __import__("subprocess")

        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"{tag}^{{commit}}"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise _failure("tag_mismatch", f"cannot resolve frozen design tag: {tag}") from error
    return result.stdout.strip()


def _check_identity(design: Mapping[str, Any], protocol: Mapping[str, Any], release: Mapping[str, Any]) -> None:
    binding = protocol.get("design_binding")
    if not isinstance(binding, dict):
        raise _failure("identity_mismatch", "protocol manifest has no design_binding")
    expected = {
        "tag": DESIGN_TAG,
        "commit": DESIGN_COMMIT,
        "design_id": DESIGN_ID,
        "freeze_id": FREEZE_ID,
        "kg_release_id": KG_RELEASE_ID,
        "kg_semantic_hash": KG_SEMANTIC_HASH,
    }
    for key, value in expected.items():
        if binding.get(key) != value:
            raise _failure("identity_mismatch", f"protocol design binding mismatch for {key}")
    if design.get("freeze_id") != FREEZE_ID or design.get("design_id") != DESIGN_ID:
        raise _failure("identity_mismatch", "freeze manifest identity mismatch")
    kg = design.get("kg_release")
    if not isinstance(kg, dict) or kg.get("release_id") != KG_RELEASE_ID or kg.get("semantic_hash") != KG_SEMANTIC_HASH:
        raise _failure("identity_mismatch", "freeze manifest KG binding mismatch")
    if release.get("release_id") != KG_RELEASE_ID or release.get("semantic_hash") != KG_SEMANTIC_HASH:
        raise _failure("identity_mismatch", "KG release identity mismatch")


def _check_design_closure(assets: Mapping[str, Any]) -> None:
    matrix = assets["capability_matrix.json"]
    evaluation = assets["evaluation_contract.json"]
    selection = assets["selection_governance.json"]
    review = assets["protocol_review.json"]
    gates = evaluation.get("gates", [])
    gate_ids = {item.get("gate_id") for item in gates if isinstance(item, dict)}
    if len(gate_ids) != len(gates):
        raise _failure("missing_reference", "evaluation gate IDs are missing or duplicated")
    cells = matrix.get("cells", [])
    cell_ids = [item.get("capability_cell_id") for item in cells if isinstance(item, dict)]
    if len(cells) != 17 or len(cell_ids) != len(set(cell_ids)):
        raise _failure("missing_reference", "capability matrix must contain 17 unique cells")
    for cell in cells:
        gate_id = cell.get("primary_gate")
        gate = next((item for item in gates if item.get("gate_id") == gate_id), None)
        if gate is None:
            raise _failure("missing_reference", f"unknown primary gate: {gate_id}")
        if cell.get("primary_failure_class") not in gate.get("failure_classes", []):
            raise _failure("missing_reference", f"failure class is not closed under gate: {cell.get('capability_cell_id')}")
    if selection.get("design_id") != DESIGN_ID or review.get("design_id") != DESIGN_ID:
        raise _failure("identity_mismatch", "design asset references are not closed")
    if review.get("decision") != "approved":
        raise _failure("identity_mismatch", "protocol review is not approved")


def load_frozen_design_bundle(
    design_root: str,
    *,
    expected_tag: str = DESIGN_TAG,
    expected_commit: str = DESIGN_COMMIT,
    repo_root: str | None = None,
) -> FrozenDesignBundle:
    root = design_root.rstrip("\\/")
    repository = _repo_root_for(root, repo_root)
    manifest = _read_json(_join(root, "freeze_manifest.json"))
    protocol_manifest = _read_json(_join(repository, PROTOCOL_MANIFEST))
    release_path = _join(repository, "kg/ontology/v1.0.0/release.json")
    release = _read_json(release_path)
    if expected_tag != DESIGN_TAG or expected_commit != DESIGN_COMMIT:
        raise _failure("identity_mismatch", "unexpected loader binding arguments")
    if _git_tag_commit(repository, expected_tag) != expected_commit:
        raise _failure("tag_mismatch", "design tag does not resolve to expected commit")
    _check_identity(manifest, protocol_manifest, release)

    assets: dict[str, Any] = {}
    for entry in manifest.get("files", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise _failure("missing_reference", "freeze manifest contains an invalid file entry")
        relative = entry["path"]
        path = _join(root, relative.rsplit("/", 1)[-1]) if relative.startswith("docs/current/benchmark/v1/") else _join(repository, relative)
        actual = _sha256(path)
        if actual != entry.get("sha256"):
            raise _failure("asset_hash_mismatch", f"frozen asset hash mismatch: {relative}")
        if relative.startswith("docs/current/benchmark/v1/") and relative != "docs/current/benchmark/v1/README.md":
            assets[relative.rsplit("/", 1)[-1]] = _read_json(path) if relative.endswith(".json") else open(path, "r", encoding="utf-8").read()

    for entry in protocol_manifest.get("frozen_inputs", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise _failure("missing_reference", "protocol manifest contains an invalid frozen input")
        relative = entry["path"]
        if relative.startswith("docs/current/benchmark/v1/"):
            design_path = _join(root, relative.rsplit("/", 1)[-1])
            if _sha256(design_path) != entry.get("sha256"):
                raise _failure("asset_hash_mismatch", f"protocol frozen input hash mismatch: {relative}")

    _check_design_closure(assets)
    kg_entry = manifest.get("kg_release", {})
    if _raw_sha256(release_path) != kg_entry.get("file_sha256"):
        raise _failure("asset_hash_mismatch", "KG release file hash mismatch")
    entities = _read_json(_join(repository, "kg/ontology/v1.0.0/entities.json"))
    policies = _read_json(_join(repository, "kg/ontology/v1.0.0/policies.json"))
    return FrozenDesignBundle(
        design_root=root,
        design_id=DESIGN_ID,
        freeze_id=FREEZE_ID,
        design_tag=expected_tag,
        design_commit=expected_commit,
        kg_release_id=KG_RELEASE_ID,
        kg_semantic_hash=KG_SEMANTIC_HASH,
        manifest=manifest,
        protocol_manifest=protocol_manifest,
        assets=assets,
        schema_document=assets["template.schema.json"],
        matrix=assets["capability_matrix.json"],
        evaluation=assets["evaluation_contract.json"],
        selection=assets["selection_governance.json"],
        protocol_review=assets["protocol_review.json"],
        kg_release=release,
        kg_entities=entities,
        kg_policies=policies,
    )
