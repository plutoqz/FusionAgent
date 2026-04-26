import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { getOperatorSummary, getRuntimeMetadata, listScenarioRuns } from "../../lib/api/client";
import { RunListRecord } from "../../lib/api/types";
import { PhaseBadge } from "../../components/status/PhaseBadge";

function sortRuns(records: RunListRecord[]) {
  return [...records].sort((left, right) => {
    const leftValue = new Date(left.updated_at ?? left.created_at ?? 0).getTime();
    const rightValue = new Date(right.updated_at ?? right.created_at ?? 0).getTime();
    return rightValue - leftValue;
  });
}

export function HomePage() {
  const { copy } = useI18n();
  const runtimeQuery = useQuery({
    queryKey: ["runtime-metadata"],
    queryFn: getRuntimeMetadata,
  });
  const summaryQuery = useQuery({
    queryKey: ["operator-summary"],
    queryFn: getOperatorSummary,
  });
  const scenariosQuery = useQuery({
    queryKey: ["scenario-runs", "dashboard"],
    queryFn: listScenarioRuns,
  });

  const recentRuns = sortRuns(summaryQuery.data?.recent_runs ?? []).slice(0, 4);
  const activeRuns = recentRuns.filter((run) => !["succeeded", "failed"].includes(run.phase)).slice(0, 3);
  const fallbackRuns = recentRuns.slice(0, 3);
  const focusRuns = activeRuns.length ? activeRuns : fallbackRuns;
  const recentScenario = scenariosQuery.data?.records[0];
  const llmConfigured = Boolean(runtimeQuery.data?.llm_provider);

  return (
    <section className="surface-page dashboard-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.home.eyebrow}</p>
          <h1>{copy.home.title}</h1>
        </div>
        <p className="surface-status">{copy.home.status(llmConfigured)}</p>
      </header>

      <section className="metric-strip" aria-label={copy.home.readinessAria}>
        <article className="metric-chip">
          <span>{copy.home.metrics.runtime.label}</span>
          <strong>{runtimeQuery.data?.llm_provider ?? copy.home.metrics.runtime.fallback}</strong>
        </article>
        <article className="metric-chip">
          <span>{copy.home.metrics.graph.label}</span>
          <strong>{runtimeQuery.data?.kg_backend ?? copy.home.metrics.graph.fallback}</strong>
        </article>
        <article className="metric-chip">
          <span>{copy.home.metrics.attention.label}</span>
          <strong>{copy.home.metrics.attention.value(summaryQuery.data?.evidence_gaps.length ?? 0)}</strong>
        </article>
      </section>

      <section className="surface-grid surface-grid--two-up dashboard-grid">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.home.focusRuns.label}</p>
            <span className="panel-marker">{copy.home.focusRuns.marker}</span>
          </div>
          {summaryQuery.isLoading ? <p className="muted-text">{copy.home.focusRuns.loading}</p> : null}
          {summaryQuery.isError ? <p className="status-error">{copy.home.focusRuns.error}</p> : null}
          {!summaryQuery.isLoading && focusRuns.length === 0 ? (
            <div className="empty-panel">
              <strong>{copy.home.focusRuns.emptyTitle}</strong>
              <p>{copy.home.focusRuns.emptyDescription}</p>
            </div>
          ) : null}
          <div className="list-stack">
            {focusRuns.map((run) => (
              <Link className="run-row run-row--stacked" key={run.run_id} to={`/runs/${run.run_id}`}>
                <div className="run-row__main">
                  <strong>{run.run_id}</strong>
                  <span>{run.trigger?.content ?? copy.home.focusRuns.noTrigger}</span>
                </div>
                <div className="run-row__meta run-row__meta--start">
                  <PhaseBadge phase={run.phase} />
                  <span>
                    {copy.runs.meta.jobTypes[run.job_type]}
                    {typeof run.progress === "number" ? ` · ${run.progress}%` : ""}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.home.quickStart.label}</p>
            <span className="panel-marker">{copy.home.quickStart.marker}</span>
          </div>
          <div className="route-list">
            <Link className="route-card" to="/runs/new" onMouseUp={(event) => event.currentTarget.blur()}>
              <span>{copy.home.quickStart.cards.newRun.label}</span>
              <strong>{copy.home.quickStart.cards.newRun.value}</strong>
            </Link>
            <Link className="route-card" to="/runs" onMouseUp={(event) => event.currentTarget.blur()}>
              <span>{copy.home.quickStart.cards.history.label}</span>
              <strong>{copy.home.quickStart.cards.history.value}</strong>
            </Link>
            <Link className="route-card" to="/scenarios" onMouseUp={(event) => event.currentTarget.blur()}>
              <span>{copy.home.quickStart.cards.reports.label}</span>
              <strong>{copy.home.quickStart.cards.reports.value}</strong>
            </Link>
            <Link className="route-card" to="/kg" onMouseUp={(event) => event.currentTarget.blur()}>
              <span>{copy.home.quickStart.cards.graph.label}</span>
              <strong>{copy.home.quickStart.cards.graph.value}</strong>
            </Link>
          </div>
        </article>
      </section>

      <section className="surface-grid surface-grid--two-up dashboard-grid">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.home.recentOutputs.label}</p>
            <span className="panel-marker">{copy.home.recentOutputs.marker}</span>
          </div>
          <dl className="status-list">
            <div>
              <dt>{copy.home.recentOutputs.items.recentRun}</dt>
              <dd>{recentRuns[0]?.run_id ?? copy.home.recentOutputs.empty}</dd>
            </div>
            <div>
              <dt>{copy.home.recentOutputs.items.recentScenario}</dt>
              <dd>{recentScenario?.scenario_name ?? recentScenario?.scenario_id ?? copy.home.recentOutputs.empty}</dd>
            </div>
            <div>
              <dt>{copy.home.recentOutputs.items.evidenceGaps}</dt>
              <dd>{copy.home.metrics.attention.value(summaryQuery.data?.evidence_gaps.length ?? 0)}</dd>
            </div>
          </dl>
          <div className="inline-actions">
            {recentRuns[0] ? (
              <Link className="inline-action inline-action--primary" to={`/runs/${recentRuns[0].run_id}`}>
                {copy.home.recentOutputs.actions.openRun}
              </Link>
            ) : null}
            <Link className="inline-action" to="/scenarios">
              {copy.home.recentOutputs.actions.openReports}
            </Link>
          </div>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.home.nextSteps.label}</p>
            <span className="panel-marker">{copy.home.nextSteps.marker}</span>
          </div>
          <div className="guide-bullets">
            {llmConfigured ? (
              <li>{copy.home.nextSteps.configured}</li>
            ) : (
              <li>{copy.home.nextSteps.unconfigured}</li>
            )}
            <li>{copy.home.nextSteps.review}</li>
            <li>{copy.home.nextSteps.explain}</li>
          </div>
          <div className="inline-actions">
            <Link className="inline-action" to={llmConfigured ? "/runs/new" : "/settings/llm"}>
              {llmConfigured ? copy.home.nextSteps.actions.createRun : copy.home.nextSteps.actions.configure}
            </Link>
            <Link className="inline-action" to="/guide">
              {copy.home.nextSteps.actions.guide}
            </Link>
          </div>
        </article>
      </section>
    </section>
  );
}
