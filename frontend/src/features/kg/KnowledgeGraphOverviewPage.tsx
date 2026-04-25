import { useQuery } from "@tanstack/react-query";

import { useI18n } from "../../app/i18n";
import { KnowledgeGraphView } from "../../components/graphs/KnowledgeGraphView";
import { getKnowledgeGraphOverview } from "../../lib/api/client";

export function KnowledgeGraphOverviewPage() {
  const { copy } = useI18n();
  const query = useQuery({
    queryKey: ["kg-overview"],
    queryFn: getKnowledgeGraphOverview,
  });

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.kgPage.overview.eyebrow}</p>
          <h1>{copy.kgPage.overview.title}</h1>
        </div>
        <p className="surface-status">{copy.kgPage.overview.status(query.data?.nodes.length ?? 0)}</p>
      </header>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.kgPage.overview.graphLabel}</p>
          <span className="panel-marker">{copy.kgPage.overview.graphMarker}</span>
        </div>
        {query.isLoading ? <p className="muted-text">{copy.kgPage.overview.loading}</p> : null}
        {query.isError ? <p className="status-error">{copy.kgPage.overview.error}</p> : null}
        {query.data ? <KnowledgeGraphView graph={query.data} mode="overview" /> : null}
      </article>
    </section>
  );
}
