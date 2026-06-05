import {
  ArtifactPreviewResponse,
  CreateRunPayload,
  KgGraphResponse,
  LlmSettingsResponse,
  LlmSettingsUpdateRequest,
  LlmSettingsValidationResponse,
  MarkdownDocumentResponse,
  OperatorRunListResponse,
  OperatorRuntimeSummaryResponse,
  RunComparisonResponse,
  RunCreateResponse,
  RunInspectionResponse,
  RunListFilters,
  ScenarioDocumentListResponse,
  ScenarioRunCreateRequest,
  ScenarioRunListResponse,
  ScenarioRunResponse,
  RuntimeMetadataResponse,
  ValidationSessionListResponse,
} from "./types";

type RequestInitWithBody = RequestInit & {
  body?: BodyInit | null;
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function resolveApiUrl(path: string) {
  return apiBaseUrl ? `${apiBaseUrl}${path}` : path;
}

export async function request<T>(path: string, init: RequestInitWithBody = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  const bodyIsFormData = init.body instanceof FormData;

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (!bodyIsFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(resolveApiUrl(path), {
    ...init,
    headers,
  });

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload =
    response.status === 204 ? null : isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String(payload.detail)
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }

  return payload as T;
}

export function getRuntimeMetadata() {
  return request<RuntimeMetadataResponse>("/api/v2/runtime");
}

export function getOperatorSummary() {
  return request<OperatorRuntimeSummaryResponse>("/api/v2/operator/summary");
}

export function listRuns(filters: RunListFilters = {}) {
  const params = new URLSearchParams();

  if (filters.limit) {
    params.set("limit", String(filters.limit));
  }
  if (filters.phase) {
    params.set("phase", filters.phase);
  }
  if (filters.jobType) {
    params.set("job_type", filters.jobType);
  }

  const query = params.toString();
  return request<OperatorRunListResponse>(query ? `/api/v2/runs?${query}` : "/api/v2/runs");
}

export function getRunInspection(runId: string) {
  return request<RunInspectionResponse>(`/api/v2/runs/${runId}/inspection`);
}

export function getRunPreview(runId: string) {
  return request<ArtifactPreviewResponse>(`/api/v2/runs/${runId}/preview`);
}

export function compareRuns(left: string, right: string) {
  return request<RunComparisonResponse>(`/api/v2/runs/${left}/compare/${right}`);
}

export function createRun(payload: CreateRunPayload) {
  const formData = new FormData();
  formData.append("job_type", payload.jobType);
  formData.append("trigger_type", payload.triggerType);
  formData.append("trigger_content", payload.triggerContent);
  formData.append("debug", payload.debug ? "true" : "false");
  formData.append("input_strategy", payload.inputStrategy);
  formData.append("field_mapping", "{}");

  if (payload.disasterType) {
    formData.append("disaster_type", payload.disasterType);
  }
  if (payload.spatialExtent) {
    formData.append("spatial_extent", payload.spatialExtent);
  }
  if (payload.temporalStart) {
    formData.append("temporal_start", payload.temporalStart);
  }
  if (payload.temporalEnd) {
    formData.append("temporal_end", payload.temporalEnd);
  }
  if (payload.targetCrs) {
    formData.append("target_crs", payload.targetCrs);
  }
  if (payload.inputStrategy === "uploaded") {
    if (payload.osmZip) {
      formData.append("osm_zip", payload.osmZip);
    }
    if (payload.refZip) {
      formData.append("ref_zip", payload.refZip);
    }
  }

  return request<RunCreateResponse>("/api/v2/runs", {
    method: "POST",
    body: formData,
  });
}

export function listScenarioRuns() {
  return request<ScenarioRunListResponse>("/api/v2/scenario-runs");
}

export function listValidationSessions() {
  return request<ValidationSessionListResponse>("/api/v2/validation/sessions");
}

export function createScenarioRun(payload: ScenarioRunCreateRequest) {
  return request<ScenarioRunResponse>("/api/v2/scenario-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resumeScenarioRun(scenarioId: string, retryFailed = false) {
  const params = new URLSearchParams();
  if (retryFailed) {
    params.set("retry_failed", "true");
  }
  const query = params.toString();
  const encodedScenarioId = encodeURIComponent(scenarioId);
  return request<ScenarioRunResponse>(`/api/v2/scenario-runs/${encodedScenarioId}/resume${query ? `?${query}` : ""}`, {
    method: "POST",
  });
}

export function listScenarioDocuments(scenarioId: string) {
  return request<ScenarioDocumentListResponse>(`/api/v2/scenario-runs/${scenarioId}/documents`);
}

export function getScenarioDocument(scenarioId: string, filename: string) {
  return request<MarkdownDocumentResponse>(
    `/api/v2/scenario-runs/${scenarioId}/documents/${encodeURIComponent(filename)}`,
  );
}

export function getKnowledgeGraphOverview() {
  return request<KgGraphResponse>("/api/v2/kg/overview");
}

export function getRunKgGraph(runId: string) {
  return request<KgGraphResponse>(`/api/v2/runs/${runId}/kg-graph`);
}

export function getLlmSettings() {
  return request<LlmSettingsResponse>("/api/v2/settings/llm");
}

export function updateLlmSettings(payload: LlmSettingsUpdateRequest) {
  return request<LlmSettingsResponse>("/api/v2/settings/llm", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function validateLlmSettings(payload: LlmSettingsUpdateRequest) {
  return request<LlmSettingsValidationResponse>("/api/v2/settings/llm/validate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
