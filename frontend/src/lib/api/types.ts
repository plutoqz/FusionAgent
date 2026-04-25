export type JobType = "building" | "road" | "water" | "poi";
export type RunPhase = "queued" | "planning" | "validating" | "running" | "healing" | "succeeded" | "failed";

export interface RunTrigger {
  type: string;
  content: string;
  disaster_type?: string | null;
  spatial_extent?: string | null;
  temporal_start?: string | null;
  temporal_end?: string | null;
}

export interface WorkflowTask {
  step: number;
  name: string;
  description: string;
  algorithm_id: string;
  depends_on: number[];
}

export interface WorkflowPlan {
  workflow_id: string;
  expected_output: string;
  estimated_time: string;
  tasks: WorkflowTask[];
}

export interface RunStatusRecord {
  run_id: string;
  job_type: JobType;
  trigger: RunTrigger;
  phase: RunPhase;
  progress: number;
  created_at: string;
  updated_at?: string | null;
  current_step?: number | null;
  failure_summary?: string | null;
}

export interface RunAuditEvent {
  timestamp: string;
  kind: string;
  message: string;
  progress: number;
  current_step?: number | null;
}

export interface RunInspectionArtifact {
  available: boolean;
  filename?: string | null;
  path?: string | null;
  size_bytes?: number | null;
  download_path?: string | null;
}

export interface RunInspectionResponse {
  run: RunStatusRecord;
  plan: WorkflowPlan | null;
  audit_events: RunAuditEvent[];
  artifact: RunInspectionArtifact;
  kg_path_trace: Record<string, unknown>;
}

export interface ArtifactPreviewResponse {
  run_id: string;
  shapefile_name?: string | null;
  geojson_path: string;
  max_features?: number;
  bbox: [number, number, number, number] | null;
  preview_feature_count: number;
  feature_count: number;
  crs?: string | null;
  geometry_types?: string[];
}

export interface RunComparisonResponse {
  left: RunInspectionResponse;
  right: RunInspectionResponse;
  differing_decisions: Record<string, { left: string | null; right: string | null }>;
}

export interface RunListRecord {
  run_id: string;
  phase: string;
  job_type: JobType;
  created_at?: string;
  updated_at?: string;
  progress?: number;
  trigger?: RunTrigger;
  run_dir?: string;
}

export interface OperatorRuntimeSummaryResponse {
  runtime: Record<string, unknown>;
  recent_runs: RunListRecord[];
  recent_scenarios: Array<Record<string, unknown>>;
  evidence_gaps: string[];
}

export interface OperatorRunListResponse {
  records: RunListRecord[];
}

export interface RuntimeMetadataResponse {
  kg_backend: string | null;
  llm_provider: string | null;
  celery_eager: string | null;
  api_port: string | null;
}

export interface RunListFilters {
  limit?: number;
  phase?: string;
  jobType?: JobType;
}

export interface CreateRunPayload {
  jobType: JobType;
  triggerType: string;
  triggerContent: string;
  disasterType?: string;
  spatialExtent?: string;
  temporalStart?: string;
  temporalEnd?: string;
  targetCrs?: string;
  debug: boolean;
  inputStrategy: "uploaded" | "task_driven_auto";
  osmZip?: File | null;
  refZip?: File | null;
}

export interface RunCreateResponse {
  run_id: string;
  phase: RunPhase;
}

export interface ScenarioRunRecord {
  scenario_id: string;
  scenario_name?: string;
  phase: string;
  child_run_ids?: string[];
}

export interface ScenarioRunListResponse {
  records: ScenarioRunRecord[];
}

export interface ScenarioRunCreateRequest {
  scenario_name: string;
  trigger_content: string;
  disaster_type?: string;
  job_types: JobType[];
  target_crs?: string;
  debug: boolean;
}

export interface ScenarioRunResponse {
  scenario_id: string;
  phase: string;
  output_dir: string;
  child_run_ids: string[];
}

export interface ScenarioDocumentEntry {
  filename: string;
  path: string;
  size_bytes: number;
  language?: string | null;
}

export interface ScenarioDocumentListResponse {
  scenario_id: string;
  documents: ScenarioDocumentEntry[];
}

export interface MarkdownDocumentResponse {
  scenario_id: string;
  filename: string;
  path: string;
  content: string;
  size_bytes: number;
  language?: string | null;
}

export interface KgGraphNode {
  id: string;
  kind: string;
  label: string;
  meta: Record<string, unknown>;
}

export interface KgGraphEdge {
  source: string;
  target: string;
  relationship: string;
  meta: Record<string, unknown>;
}

export interface KgGraphResponse {
  nodes: KgGraphNode[];
  edges: KgGraphEdge[];
  meta: Record<string, unknown>;
}

export interface LlmSettingsResponse {
  provider: string | null;
  base_url: string | null;
  model: string | null;
  timeout_sec: number | null;
  has_api_key: boolean;
  api_key_masked: string | null;
}

export interface LlmSettingsUpdateRequest {
  provider?: string | null;
  base_url?: string | null;
  api_key?: string | null;
  model?: string | null;
  timeout_sec?: number | null;
}

export interface LlmSettingsValidationResponse {
  valid: boolean;
  settings: LlmSettingsResponse;
}
