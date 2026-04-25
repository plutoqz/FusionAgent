import { Link } from "react-router-dom";

import { useI18n } from "../../app/i18n";

export function HomePage() {
  const { copy } = useI18n();

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.home.eyebrow}</p>
          <h1>{copy.home.title}</h1>
        </div>
        <p className="surface-status">{copy.home.status}</p>
      </header>

      <section className="metric-strip" aria-label={copy.home.readinessAria}>
        <article className="metric-chip">
          <span>{copy.home.metrics.apiBoundary.label}</span>
          <strong>{copy.home.metrics.apiBoundary.value}</strong>
        </article>
        <article className="metric-chip">
          <span>{copy.home.metrics.graphPayloads.label}</span>
          <strong>{copy.home.metrics.graphPayloads.value}</strong>
        </article>
        <article className="metric-chip">
          <span>{copy.home.metrics.settingsFlow.label}</span>
          <strong>{copy.home.metrics.settingsFlow.value}</strong>
        </article>
      </section>

      <section className="surface-grid surface-grid--two-up">
        <article className="surface-panel">
          <div className="panel-heading">
            <p className="panel-label">{copy.home.immediateSurfaces.label}</p>
            <span className="panel-marker">{copy.home.immediateSurfaces.marker}</span>
          </div>
          <div className="route-list">
            <Link className="route-card" to="/runs/new">
              <span>{copy.home.immediateSurfaces.cards.createRun.label}</span>
              <strong>{copy.home.immediateSurfaces.cards.createRun.value}</strong>
            </Link>
            <Link className="route-card" to="/runs">
              <span>{copy.home.immediateSurfaces.cards.runRegistry.label}</span>
              <strong>{copy.home.immediateSurfaces.cards.runRegistry.value}</strong>
            </Link>
            <Link className="route-card" to="/scenarios">
              <span>{copy.home.immediateSurfaces.cards.scenarios.label}</span>
              <strong>{copy.home.immediateSurfaces.cards.scenarios.value}</strong>
            </Link>
            <Link className="route-card" to="/guide">
              <span>{copy.home.immediateSurfaces.cards.guide.label}</span>
              <strong>{copy.home.immediateSurfaces.cards.guide.value}</strong>
            </Link>
          </div>
        </article>

        <article className="surface-panel">
          <div className="panel-heading">
            <p className="panel-label">{copy.home.readinessLedger.label}</p>
            <span className="panel-marker">{copy.home.readinessLedger.marker}</span>
          </div>
          <dl className="status-list">
            <div>
              <dt>{copy.home.readinessLedger.items.kgOverview}</dt>
              <dd>/api/v2/kg/overview</dd>
            </div>
            <div>
              <dt>{copy.home.readinessLedger.items.runGraph}</dt>
              <dd>/api/v2/runs/:id/kg-graph</dd>
            </div>
            <div>
              <dt>{copy.home.readinessLedger.items.previewMap}</dt>
              <dd>/api/v2/runs/:id/preview</dd>
            </div>
            <div>
              <dt>{copy.home.readinessLedger.items.llmSettings}</dt>
              <dd>/api/v2/settings/llm</dd>
            </div>
          </dl>
        </article>
      </section>
    </section>
  );
}
