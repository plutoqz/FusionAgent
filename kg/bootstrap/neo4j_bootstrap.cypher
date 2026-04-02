// Auto-generated GeoFusion bootstrap for Neo4j.

// Safe to replay because every statement uses IF NOT EXISTS or MERGE.

CREATE CONSTRAINT workflow_pattern_pattern_id IF NOT EXISTS
FOR (wp:WorkflowPattern) REQUIRE wp.patternId IS UNIQUE;
CREATE CONSTRAINT algorithm_algo_id IF NOT EXISTS
FOR (algo:Algorithm) REQUIRE algo.algoId IS UNIQUE;
CREATE CONSTRAINT datasource_source_id IF NOT EXISTS
FOR (ds:DataSource) REQUIRE ds.sourceId IS UNIQUE;
CREATE CONSTRAINT datatype_type_id IF NOT EXISTS
FOR (dt:DataType) REQUIRE dt.typeId IS UNIQUE;
CREATE CONSTRAINT step_template_step_key IF NOT EXISTS
FOR (st:StepTemplate) REQUIRE st.stepKey IS UNIQUE;
CREATE CONSTRAINT workflow_instance_instance_id IF NOT EXISTS
FOR (run:WorkflowInstance) REQUIRE run.instanceId IS UNIQUE;
CREATE FULLTEXT INDEX wp_search IF NOT EXISTS
FOR (wp:WorkflowPattern) ON EACH [wp.patternId, wp.patternName];
CREATE FULLTEXT INDEX algo_search IF NOT EXISTS
FOR (algo:Algorithm) ON EACH [algo.algoId, algo.algoName];
CREATE FULLTEXT INDEX ds_search IF NOT EXISTS
FOR (ds:DataSource) ON EACH [ds.sourceId, ds.sourceName];

// Seed DataType nodes
MERGE (dt:DataType {typeId: "dt.raw.vector"}) SET dt += {theme: "generic", geometryType: "mixed", description: "Uploaded raw vector bundle."};
MERGE (dt:DataType {typeId: "dt.building.bundle"}) SET dt += {theme: "building", geometryType: "polygon", description: "Prepared building fusion input bundle."};
MERGE (dt:DataType {typeId: "dt.road.bundle"}) SET dt += {theme: "transportation", geometryType: "line", description: "Prepared road fusion input bundle."};
MERGE (dt:DataType {typeId: "dt.building.fused"}) SET dt += {theme: "building", geometryType: "polygon", description: "Fused building output."};
MERGE (dt:DataType {typeId: "dt.road.fused"}) SET dt += {theme: "transportation", geometryType: "line", description: "Fused road output."};

// Seed Algorithm nodes and alternatives
MERGE (algo:Algorithm {algoId: "algo.fusion.building.v1"}) SET algo += {algoId: "algo.fusion.building.v1", algoName: "Building Fusion Legacy", inputTypes: ["dt.building.bundle"], outputType: "dt.building.fused", taskType: "building_fusion", toolRef: "adapters.building_adapter:run_building_fusion", successRate: 0.92};
MERGE (algo:Algorithm {algoId: "algo.fusion.building.safe"}) SET algo += {algoId: "algo.fusion.building.safe", algoName: "Building Fusion Safe Fallback", inputTypes: ["dt.building.bundle"], outputType: "dt.building.fused", taskType: "building_fusion", toolRef: "adapters.building_adapter:run_building_fusion", successRate: 0.75};
MERGE (algo:Algorithm {algoId: "algo.fusion.road.v1"}) SET algo += {algoId: "algo.fusion.road.v1", algoName: "Road Fusion Legacy", inputTypes: ["dt.road.bundle"], outputType: "dt.road.fused", taskType: "road_fusion", toolRef: "adapters.road_adapter:run_road_fusion", successRate: 0.9};
MERGE (algo:Algorithm {algoId: "algo.fusion.road.safe"}) SET algo += {algoId: "algo.fusion.road.safe", algoName: "Road Fusion Safe Fallback", inputTypes: ["dt.road.bundle"], outputType: "dt.road.fused", taskType: "road_fusion", toolRef: "adapters.road_adapter:run_road_fusion", successRate: 0.72};
MERGE (algo:Algorithm {algoId: "algo.transform.raw_to_building_bundle"}) SET algo += {algoId: "algo.transform.raw_to_building_bundle", algoName: "Raw Vector to Building Bundle", inputTypes: ["dt.raw.vector"], outputType: "dt.building.bundle", taskType: "transform", toolRef: "builtin:transform", successRate: 0.98};
MERGE (algo:Algorithm {algoId: "algo.transform.raw_to_road_bundle"}) SET algo += {algoId: "algo.transform.raw_to_road_bundle", algoName: "Raw Vector to Road Bundle", inputTypes: ["dt.raw.vector"], outputType: "dt.road.bundle", taskType: "transform", toolRef: "builtin:transform", successRate: 0.98};
MATCH (src:Algorithm {algoId: "algo.fusion.building.v1"}), (dst:Algorithm {algoId: "algo.fusion.building.safe"}) MERGE (src)-[:ALTERNATIVE_TO]->(dst);
MATCH (src:Algorithm {algoId: "algo.fusion.building.safe"}), (dst:Algorithm {algoId: "algo.fusion.building.v1"}) MERGE (src)-[:ALTERNATIVE_TO]->(dst);
MATCH (src:Algorithm {algoId: "algo.fusion.road.v1"}), (dst:Algorithm {algoId: "algo.fusion.road.safe"}) MERGE (src)-[:ALTERNATIVE_TO]->(dst);
MATCH (src:Algorithm {algoId: "algo.fusion.road.safe"}), (dst:Algorithm {algoId: "algo.fusion.road.v1"}) MERGE (src)-[:ALTERNATIVE_TO]->(dst);

// Seed DataSource nodes
MERGE (ds:DataSource {sourceId: "upload.bundle"}) SET ds += {sourceId: "upload.bundle", sourceName: "Uploaded Bundle", supportedTypes: ["dt.building.bundle", "dt.road.bundle", "dt.raw.vector"], disasterTypes: ["generic", "flood", "earthquake", "typhoon"], qualityScore: 1.0, metadataJson: "{\"kind\": \"local\"}"};
MERGE (ds:DataSource {sourceId: "catalog.flood.building"}) SET ds += {sourceId: "catalog.flood.building", sourceName: "Flood Building Catalog", supportedTypes: ["dt.building.bundle"], disasterTypes: ["flood", "generic"], qualityScore: 0.86, metadataJson: "{\"kind\": \"catalog\", \"priority\": 2}"};
MERGE (ds:DataSource {sourceId: "catalog.earthquake.road"}) SET ds += {sourceId: "catalog.earthquake.road", sourceName: "Earthquake Road Catalog", supportedTypes: ["dt.road.bundle"], disasterTypes: ["earthquake", "generic"], qualityScore: 0.84, metadataJson: "{\"kind\": \"catalog\", \"priority\": 2}"};

// Seed WorkflowPattern and StepTemplate nodes
MERGE (wp:WorkflowPattern {patternId: "wp.flood.building.default"}) SET wp += {patternId: "wp.flood.building.default", patternName: "Flood Building Fusion", jobType: "building", disasterTypes: ["flood", "typhoon", "generic"], successRate: 0.88, metadataJson: "{\"version\": \"1.0.0\"}"};
MERGE (st:StepTemplate {stepKey: "wp.flood.building.default#1"}) SET st += {stepKey: "wp.flood.building.default#1", order: 1, name: "building_fusion", algorithmId: "algo.fusion.building.v1", inputDataType: "dt.building.bundle", outputDataType: "dt.building.fused", dataSourceId: "upload.bundle", dependsOn: [], isOptional: false};
MATCH (wp:WorkflowPattern {patternId: "wp.flood.building.default"}), (st:StepTemplate {stepKey: "wp.flood.building.default#1"}) MERGE (wp)-[:HAS_STEP {order: 1}]->(st);
MERGE (wp:WorkflowPattern {patternId: "wp.flood.building.safe"}) SET wp += {patternId: "wp.flood.building.safe", patternName: "Flood Building Fusion Safe Route", jobType: "building", disasterTypes: ["flood", "generic"], successRate: 0.82, metadataJson: "{\"version\": \"1.0.0\", \"mode\": \"safe\"}"};
MERGE (st:StepTemplate {stepKey: "wp.flood.building.safe#1"}) SET st += {stepKey: "wp.flood.building.safe#1", order: 1, name: "building_fusion_safe", algorithmId: "algo.fusion.building.safe", inputDataType: "dt.building.bundle", outputDataType: "dt.building.fused", dataSourceId: "upload.bundle", dependsOn: [], isOptional: false};
MATCH (wp:WorkflowPattern {patternId: "wp.flood.building.safe"}), (st:StepTemplate {stepKey: "wp.flood.building.safe#1"}) MERGE (wp)-[:HAS_STEP {order: 1}]->(st);
MERGE (wp:WorkflowPattern {patternId: "wp.flood.road.default"}) SET wp += {patternId: "wp.flood.road.default", patternName: "Flood Road Fusion", jobType: "road", disasterTypes: ["flood", "earthquake", "generic"], successRate: 0.86, metadataJson: "{\"version\": \"1.0.0\"}"};
MERGE (st:StepTemplate {stepKey: "wp.flood.road.default#1"}) SET st += {stepKey: "wp.flood.road.default#1", order: 1, name: "road_fusion", algorithmId: "algo.fusion.road.v1", inputDataType: "dt.road.bundle", outputDataType: "dt.road.fused", dataSourceId: "upload.bundle", dependsOn: [], isOptional: false};
MATCH (wp:WorkflowPattern {patternId: "wp.flood.road.default"}), (st:StepTemplate {stepKey: "wp.flood.road.default#1"}) MERGE (wp)-[:HAS_STEP {order: 1}]->(st);
MERGE (wp:WorkflowPattern {patternId: "wp.flood.road.safe"}) SET wp += {patternId: "wp.flood.road.safe", patternName: "Flood Road Fusion Safe Route", jobType: "road", disasterTypes: ["earthquake", "generic"], successRate: 0.81, metadataJson: "{\"version\": \"1.0.0\", \"mode\": \"safe\"}"};
MERGE (st:StepTemplate {stepKey: "wp.flood.road.safe#1"}) SET st += {stepKey: "wp.flood.road.safe#1", order: 1, name: "road_fusion_safe", algorithmId: "algo.fusion.road.safe", inputDataType: "dt.road.bundle", outputDataType: "dt.road.fused", dataSourceId: "upload.bundle", dependsOn: [], isOptional: false};
MATCH (wp:WorkflowPattern {patternId: "wp.flood.road.safe"}), (st:StepTemplate {stepKey: "wp.flood.road.safe#1"}) MERGE (wp)-[:HAS_STEP {order: 1}]->(st);

// Seed transform graph
MATCH (src:DataType {typeId: "dt.raw.vector"}), (dst:DataType {typeId: "dt.building.bundle"}) MERGE (src)-[:CAN_TRANSFORM_TO]->(dst);
MATCH (src:DataType {typeId: "dt.raw.vector"}), (dst:DataType {typeId: "dt.road.bundle"}) MERGE (src)-[:CAN_TRANSFORM_TO]->(dst);