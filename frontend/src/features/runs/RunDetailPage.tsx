import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { ArtifactPreviewMap } from "../../components/maps/ArtifactPreviewMap";
import { getRunInspection, getRunPreview } from "../../lib/api/client";
import { PhaseBadge } from "../../components/status/PhaseBadge";

function summarizeTrace(trace: Record<string, unknown>) {
  return Object.entries(trace)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .slice(0, 4);
}

export function RunDetailPage() {
  const { copy } = useI18n();
  const { runId = "" } = useParams();

  const inspectionQuery = useQuery({
    queryKey: ["run-inspection", runId],
    queryFn: () => getRunInspection(runId),
    enabled: Boolean(runId),
  });

  const previewQuery = useQuery({
    queryKey: ["run-preview", runId],
    queryFn: () => getRunPreview(runId),
    enabled: Boolean(runId),
  });

  const inspection = inspectionQuery.data;
  const preview = previewQuery.data;
  const traceSummary = summarizeTrace(inspection?.kg_path_trace ?? {});

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.runs.detail.eyebrow}</p>
          <h1>{runId || copy.runs.detail.fallbackTitle}</h1>
        </div>
        <div className="detail-status">
          <PhaseBadge phase={inspection?.run.phase ?? "queued"} />
          <span className="detail-status__meta">
            {inspection?.run.job_type ? copy.runs.meta.jobTypes[inspection.run.job_type] : copy.runs.detail.noJobLoaded}
          </span>
        </div>
      </header>

      <section className="surface-grid">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.detail.runSummary}</p>
            <span className="panel-marker">{inspection?.run.progress ?? 0}%</span>
          </div>
          <strong className="panel-state">{inspection?.run.trigger.content ?? copy.runs.detail.selectRun}</strong>
          <dl className="status-list status-list--compact">
            <div>
              <dt>{copy.runs.detail.summaryItems.jobType}</dt>
              <dd>{inspection?.run.job_type ? copy.runs.meta.jobTypes[inspection.run.job_type] : "-"}</dd>
            </div>
            <div>
              <dt>{copy.runs.detail.summaryItems.createdAt}</dt>
              <dd>{inspection?.run.created_at ?? "-"}</dd>
            </div>
            <div>
              <dt>{copy.runs.detail.summaryItems.updatedAt}</dt>
              <dd>{inspection?.run.updated_at ?? "-"}</dd>
            </div>
          </dl>
          <p className="muted-text">
            {inspection?.run.failure_summary ?? copy.runs.detail.noSnapshot}
          </p>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.detail.artifactPreview}</p>
            <span className="panel-marker">{`${preview?.preview_feature_count ?? 0}${copy.runs.detail.featuresSuffix}`}</span>
          </div>
          {preview ? (
            <>
              <strong className="panel-state">{copy.runs.detail.totalFeatures(preview.feature_count)}</strong>
              <p className="muted-text">
                {preview.bbox ? `BBox ${preview.bbox.join(", ")}` : copy.runs.detail.bboxPending}
              </p>
              <ArtifactPreviewMap
                geojsonUrl={preview.geojson_path}
                bbox={preview.bbox}
                featureCount={preview.preview_feature_count}
                crs={preview.crs}
              />
              <div className="inline-actions">
                <a className="inline-action" href={preview.geojson_path} target="_blank" rel="noreferrer">
                  {copy.runs.detail.openGeojson}
                </a>
                {inspection?.artifact.download_path ? (
                  <a className="inline-action inline-action--primary" href={inspection.artifact.download_path} target="_blank" rel="noreferrer">
                    {copy.runs.detail.downloadArtifact}
                  </a>
                ) : null}
              </div>
            </>
          ) : (
            <p className="muted-text">
              {previewQuery.isError ? copy.runs.detail.previewNotReady : copy.runs.detail.previewPending}
            </p>
          )}
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.detail.evidenceSnapshot}</p>
            <span className="panel-marker">{`${inspection?.audit_events.length ?? 0}${copy.runs.detail.entriesSuffix}`}</span>
          </div>
          <strong className="panel-state">
            {inspection?.artifact.available ? inspection.artifact.filename ?? copy.runs.detail.artifactReady : copy.runs.detail.artifactPending}
          </strong>
          <p className="muted-text">
            {inspection?.artifact.download_path ?? copy.runs.detail.noDownloadPath}
          </p>
          <div className="inline-actions">
            <Link className="inline-action" to="/runs">
              {copy.runs.detail.actions.backToHistory}
            </Link>
            {runId ? (
              <Link className="inline-action" to={`/runs/compare?left=${runId}`}>
                {copy.runs.detail.actions.compareFromHere}
              </Link>
            ) : null}
          </div>
        </article>
      </section>

      <section className="surface-grid surface-grid--two-up">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.detail.workflowPlan}</p>
            <span className="panel-marker">{inspection?.plan?.workflow_id ?? copy.runs.detail.unassigned}</span>
          </div>
          {inspectionQuery.isLoading ? <p className="muted-text">{copy.runs.detail.loadingPlan}</p> : null}
          {inspectionQuery.isError ? <p className="status-error">{copy.runs.detail.loadPlanFailed}</p> : null}
          {inspection?.plan?.tasks?.length ? (
            <ol className="timeline">
              {inspection.plan.tasks.map((task) => (
                <li className="timeline-row" key={`${task.step}-${task.algorithm_id}`}>
                  <strong>{task.name}</strong>
                  <span>{copy.runs.detail.stepLabel(task.step, task.algorithm_id)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-text">{copy.runs.detail.planUnavailable}</p>
          )}
          <div className="panel-divider" />
          <div className="panel-heading panel-heading--tight">
            <p className="panel-label">{copy.runs.detail.reasoningTrace}</p>
            <span className="panel-marker">{traceSummary.length}</span>
          </div>
          {traceSummary.length ? (
            <dl className="status-list status-list--compact">
              {traceSummary.map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{Array.isArray(value) ? value.join(", ") : String(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="muted-text">{copy.runs.detail.reasoningPending}</p>
          )}
          {runId ? (
            <div className="inline-actions">
              <Link className="inline-action inline-action--primary" to={`/kg/runs/${runId}`}>
                {copy.kgPage.runPath.title}
              </Link>
            </div>
          ) : null}
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.detail.auditTimeline}</p>
            <span className="panel-marker">{`${inspection?.audit_events.length ?? 0}${copy.runs.detail.entriesSuffix}`}</span>
          </div>
          {inspection?.audit_events.length ? (
            <ol className="timeline">
              {inspection.audit_events.map((event) => (
                <li className="timeline-row" key={`${event.timestamp}-${event.kind}-${event.message}`}>
                  <strong>{event.kind}</strong>
                  <span>{event.message}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted-text">{copy.runs.detail.auditPending}</p>
          )}
          <div className="panel-divider" />
          <div className="panel-heading panel-heading--tight">
            <p className="panel-label">{copy.runs.detail.relatedActions}</p>
            <span className="panel-marker">{copy.runs.detail.relatedMarker}</span>
          </div>
          <div className="inline-actions">
            <Link className="inline-action" to="/scenarios">
              {copy.runs.detail.actions.openReports}
            </Link>
            <Link className="inline-action" to="/guide">
              {copy.runs.detail.actions.openGuide}
            </Link>
          </div>
        </article>
      </section>
    </section>
  );
}
