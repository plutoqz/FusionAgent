import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { KnowledgeGraphView } from "../../components/graphs/KnowledgeGraphView";
import { getRunKgGraph } from "../../lib/api/client";

export function RunPathGraphPage() {
  const { copy } = useI18n();
  const { runId = "" } = useParams();
  const query = useQuery({
    queryKey: ["run-kg-graph", runId],
    queryFn: () => getRunKgGraph(runId),
    enabled: Boolean(runId),
  });

  const groundingReport = (query.data?.meta.grounding_report as Record<string, unknown> | undefined) ?? {};

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.kgPage.runPath.eyebrow}</p>
          <h1>{runId || copy.kgPage.runPath.title}</h1>
        </div>
        <p className="surface-status">{copy.kgPage.runPath.status}</p>
      </header>

      <section className="surface-grid surface-grid--two-up">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.kgPage.runPath.graphLabel}</p>
            <span className="panel-marker">{copy.kgPage.runPath.graphMarker}</span>
          </div>
          {query.isLoading ? <p className="muted-text">{copy.kgPage.runPath.loading}</p> : null}
          {query.isError ? <p className="status-error">{copy.kgPage.runPath.error}</p> : null}
          {query.data ? <KnowledgeGraphView graph={query.data} mode="run_path" /> : null}
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.kgPage.runPath.groundingLabel}</p>
            <span className="panel-marker">{String(query.data?.meta.workflow_id ?? "-")}</span>
          </div>
          <dl className="status-list">
            <div>
              <dt>{copy.kgPage.runPath.selectedPattern}</dt>
              <dd>{String(query.data?.meta.selected_pattern_id ?? "-")}</dd>
            </div>
            <div>
              <dt>{copy.kgPage.runPath.groundedSteps}</dt>
              <dd>{String(groundingReport.grounded_step_count ?? "-")}</dd>
            </div>
            <div>
              <dt>{copy.kgPage.runPath.totalSteps}</dt>
              <dd>{String(groundingReport.total_step_count ?? query.data?.meta.task_count ?? "-")}</dd>
            </div>
          </dl>
        </article>
      </section>
    </section>
  );
}
