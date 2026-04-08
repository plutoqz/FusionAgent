from __future__ import annotations

from typing import Dict, List

from schemas.fusion import JobType

from kg.models import AlgorithmNode, AlgorithmParameterSpec, DataSourceNode, DataTypeNode, PatternStep, WorkflowPatternNode


DATA_TYPES: Dict[str, DataTypeNode] = {
    "dt.raw.vector": DataTypeNode(
        type_id="dt.raw.vector",
        theme="generic",
        geometry_type="mixed",
        description="Uploaded raw vector bundle.",
    ),
    "dt.building.bundle": DataTypeNode(
        type_id="dt.building.bundle",
        theme="building",
        geometry_type="polygon",
        description="Prepared building fusion input bundle.",
    ),
    "dt.road.bundle": DataTypeNode(
        type_id="dt.road.bundle",
        theme="transportation",
        geometry_type="line",
        description="Prepared road fusion input bundle.",
    ),
    "dt.building.fused": DataTypeNode(
        type_id="dt.building.fused",
        theme="building",
        geometry_type="polygon",
        description="Fused building output.",
    ),
    "dt.road.fused": DataTypeNode(
        type_id="dt.road.fused",
        theme="transportation",
        geometry_type="line",
        description="Fused road output.",
    ),
}


ALGORITHMS: Dict[str, AlgorithmNode] = {
    "algo.fusion.building.v1": AlgorithmNode(
        algo_id="algo.fusion.building.v1",
        algo_name="Building Fusion Legacy",
        input_types=["dt.building.bundle"],
        output_type="dt.building.fused",
        task_type="building_fusion",
        tool_ref="adapters.building_adapter:run_building_fusion",
        success_rate=0.92,
        alternatives=["algo.fusion.building.safe"],
    ),
    "algo.fusion.building.safe": AlgorithmNode(
        algo_id="algo.fusion.building.safe",
        algo_name="Building Fusion Safe Fallback",
        input_types=["dt.building.bundle"],
        output_type="dt.building.fused",
        task_type="building_fusion",
        tool_ref="adapters.building_adapter:run_building_fusion",
        success_rate=0.75,
        alternatives=["algo.fusion.building.v1"],
    ),
    "algo.fusion.road.v1": AlgorithmNode(
        algo_id="algo.fusion.road.v1",
        algo_name="Road Fusion Legacy",
        input_types=["dt.road.bundle"],
        output_type="dt.road.fused",
        task_type="road_fusion",
        tool_ref="adapters.road_adapter:run_road_fusion",
        success_rate=0.9,
        alternatives=["algo.fusion.road.safe"],
    ),
    "algo.fusion.road.safe": AlgorithmNode(
        algo_id="algo.fusion.road.safe",
        algo_name="Road Fusion Safe Fallback",
        input_types=["dt.road.bundle"],
        output_type="dt.road.fused",
        task_type="road_fusion",
        tool_ref="adapters.road_adapter:run_road_fusion",
        success_rate=0.72,
        alternatives=["algo.fusion.road.v1"],
    ),
    "algo.transform.raw_to_building_bundle": AlgorithmNode(
        algo_id="algo.transform.raw_to_building_bundle",
        algo_name="Raw Vector to Building Bundle",
        input_types=["dt.raw.vector"],
        output_type="dt.building.bundle",
        task_type="transform",
        tool_ref="builtin:transform",
        success_rate=0.98,
    ),
    "algo.transform.raw_to_road_bundle": AlgorithmNode(
        algo_id="algo.transform.raw_to_road_bundle",
        algo_name="Raw Vector to Road Bundle",
        input_types=["dt.raw.vector"],
        output_type="dt.road.bundle",
        task_type="transform",
        tool_ref="builtin:transform",
        success_rate=0.98,
    ),
}

PARAMETER_SPECS: Dict[str, List[AlgorithmParameterSpec]] = {
    # Building fusion parameters are derived from legacy adapter semantics:
    # - match similarity threshold: label=1 when similarity > threshold
    # - one-to-one thresholds: sim_area/sim_shape/sim_overlap must each be >= threshold
    "algo.fusion.building.v1": [
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.building.v1.match_similarity_threshold",
            algo_id="algo.fusion.building.v1",
            key="match_similarity_threshold",
            label="Match Similarity Threshold",
            param_type="float",
            default=0.3,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
            description="Pairs with similarity > this value are treated as matched (legacy label=1).",
            required=False,
            order=10,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.building.v1.one_to_one_min_area_similarity",
            algo_id="algo.fusion.building.v1",
            key="one_to_one_min_area_similarity",
            label="One-to-One Min Area Similarity",
            param_type="float",
            default=0.3,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
            description="For 1:1 matches, sim_area must be >= this value to fuse as one-to-one.",
            required=False,
            order=20,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.building.v1.one_to_one_min_shape_similarity",
            algo_id="algo.fusion.building.v1",
            key="one_to_one_min_shape_similarity",
            label="One-to-One Min Shape Similarity",
            param_type="float",
            default=0.3,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
            description="For 1:1 matches, sim_shape must be >= this value to fuse as one-to-one.",
            required=False,
            order=30,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.building.v1.one_to_one_min_overlap_similarity",
            algo_id="algo.fusion.building.v1",
            key="one_to_one_min_overlap_similarity",
            label="One-to-One Min Overlap Similarity",
            param_type="float",
            default=0.3,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
            description="For 1:1 matches, sim_overlap must be >= this value to fuse as one-to-one.",
            required=False,
            order=40,
        ),
    ],
    "algo.fusion.building.safe": [
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.building.safe.match_similarity_threshold",
            algo_id="algo.fusion.building.safe",
            key="match_similarity_threshold",
            label="Match Similarity Threshold",
            param_type="float",
            default=0.4,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
            description="Conservative match threshold for safe mode.",
            required=False,
            order=10,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.building.safe.one_to_one_min_overlap_similarity",
            algo_id="algo.fusion.building.safe",
            key="one_to_one_min_overlap_similarity",
            label="One-to-One Min Overlap Similarity",
            param_type="float",
            default=0.4,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
            description="Conservative one-to-one overlap threshold for safe mode.",
            required=False,
            order=20,
        ),
    ],
    # Road fusion parameters are derived from legacy algorithm constants and adapter defaults:
    # - ANGLE_THRESHOLD / SNAP_TOLERANCE / BUFFER_DIST / MAX_HAUSDORFF in Algorithm/line.py
    # - dedupe buffer_distance default in adapters/road_adapter.py
    "algo.fusion.road.v1": [
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.road.v1.angle_threshold_deg",
            algo_id="algo.fusion.road.v1",
            key="angle_threshold_deg",
            label="Split Angle Threshold",
            param_type="int",
            default=135,
            min_value=0.0,
            max_value=180.0,
            unit="deg",
            description="Split lines at sharp turns: angles below this threshold trigger a split.",
            required=False,
            order=10,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.road.v1.snap_tolerance_m",
            algo_id="algo.fusion.road.v1",
            key="snap_tolerance_m",
            label="Snap Tolerance",
            param_type="float",
            default=1.0,
            min_value=0.0,
            max_value=10.0,
            unit="m",
            description="Endpoint snap tolerance used when normalizing line endpoints.",
            required=False,
            order=20,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.road.v1.match_buffer_m",
            algo_id="algo.fusion.road.v1",
            key="match_buffer_m",
            label="Match Buffer Distance",
            param_type="float",
            default=20.0,
            min_value=0.0,
            max_value=100.0,
            unit="m",
            description="Buffer radius for candidate matching between OSM and reference lines.",
            required=False,
            order=30,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.road.v1.max_hausdorff_m",
            algo_id="algo.fusion.road.v1",
            key="max_hausdorff_m",
            label="Max Hausdorff Distance",
            param_type="float",
            default=15.0,
            min_value=0.0,
            max_value=100.0,
            unit="m",
            description="Maximum Hausdorff distance allowed to consider two lines as a match.",
            required=False,
            order=40,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.road.v1.dedupe_buffer_m",
            algo_id="algo.fusion.road.v1",
            key="dedupe_buffer_m",
            label="Dedupe Buffer Distance",
            param_type="float",
            default=15.0,
            min_value=0.0,
            max_value=100.0,
            unit="m",
            description="Buffer distance used during post-fusion deduplication.",
            required=False,
            order=50,
        ),
    ],
    "algo.fusion.road.safe": [
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.road.safe.max_hausdorff_m",
            algo_id="algo.fusion.road.safe",
            key="max_hausdorff_m",
            label="Max Hausdorff Distance",
            param_type="float",
            default=10.0,
            min_value=0.0,
            max_value=100.0,
            unit="m",
            description="Conservative Hausdorff threshold for safe mode.",
            required=False,
            order=10,
        ),
        AlgorithmParameterSpec(
            spec_id="ps.algo.fusion.road.safe.dedupe_buffer_m",
            algo_id="algo.fusion.road.safe",
            key="dedupe_buffer_m",
            label="Dedupe Buffer Distance",
            param_type="float",
            default=12.0,
            min_value=0.0,
            max_value=100.0,
            unit="m",
            description="Conservative dedupe buffer for safe mode.",
            required=False,
            order=20,
        ),
    ],
}


WORKFLOW_PATTERNS: List[WorkflowPatternNode] = [
    WorkflowPatternNode(
        pattern_id="wp.flood.building.default",
        pattern_name="Flood Building Fusion",
        job_type=JobType.building,
        disaster_types=["flood", "typhoon", "generic"],
        success_rate=0.88,
        metadata={"version": "1.0.0"},
        steps=[
            PatternStep(
                order=1,
                name="building_fusion",
                algorithm_id="algo.fusion.building.v1",
                input_data_type="dt.building.bundle",
                output_data_type="dt.building.fused",
                data_source_id="upload.bundle",
            )
        ],
    ),
    WorkflowPatternNode(
        pattern_id="wp.flood.building.safe",
        pattern_name="Flood Building Fusion Safe Route",
        job_type=JobType.building,
        disaster_types=["flood", "generic"],
        success_rate=0.82,
        metadata={"version": "1.0.0", "mode": "safe"},
        steps=[
            PatternStep(
                order=1,
                name="building_fusion_safe",
                algorithm_id="algo.fusion.building.safe",
                input_data_type="dt.building.bundle",
                output_data_type="dt.building.fused",
                data_source_id="upload.bundle",
            )
        ],
    ),
    WorkflowPatternNode(
        pattern_id="wp.flood.road.default",
        pattern_name="Flood Road Fusion",
        job_type=JobType.road,
        disaster_types=["flood", "earthquake", "generic"],
        success_rate=0.86,
        metadata={"version": "1.0.0"},
        steps=[
            PatternStep(
                order=1,
                name="road_fusion",
                algorithm_id="algo.fusion.road.v1",
                input_data_type="dt.road.bundle",
                output_data_type="dt.road.fused",
                data_source_id="upload.bundle",
            )
        ],
    ),
    WorkflowPatternNode(
        pattern_id="wp.flood.road.safe",
        pattern_name="Flood Road Fusion Safe Route",
        job_type=JobType.road,
        disaster_types=["earthquake", "generic"],
        success_rate=0.81,
        metadata={"version": "1.0.0", "mode": "safe"},
        steps=[
            PatternStep(
                order=1,
                name="road_fusion_safe",
                algorithm_id="algo.fusion.road.safe",
                input_data_type="dt.road.bundle",
                output_data_type="dt.road.fused",
                data_source_id="upload.bundle",
            )
        ],
    ),
]


DATA_SOURCES: List[DataSourceNode] = [
    DataSourceNode(
        source_id="upload.bundle",
        source_name="Uploaded Bundle",
        supported_types=["dt.building.bundle", "dt.road.bundle", "dt.raw.vector"],
        disaster_types=["generic", "flood", "earthquake", "typhoon"],
        quality_score=1.0,
        metadata={"kind": "local"},
    ),
    DataSourceNode(
        source_id="catalog.flood.building",
        source_name="Flood Building Catalog",
        supported_types=["dt.building.bundle"],
        disaster_types=["flood", "generic"],
        quality_score=0.86,
        metadata={"kind": "catalog", "priority": 2},
    ),
    DataSourceNode(
        source_id="catalog.earthquake.road",
        source_name="Earthquake Road Catalog",
        supported_types=["dt.road.bundle"],
        disaster_types=["earthquake", "generic"],
        quality_score=0.84,
        metadata={"kind": "catalog", "priority": 2},
    ),
]


CAN_TRANSFORM_TO: Dict[str, List[str]] = {
    "dt.raw.vector": ["dt.building.bundle", "dt.road.bundle"],
}
