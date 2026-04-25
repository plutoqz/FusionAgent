import { Link } from "react-router-dom";

import { useI18n } from "../../app/i18n";

export function GuidePage() {
  const { copy } = useI18n();

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.guidePage.eyebrow}</p>
          <h1>{copy.guidePage.title}</h1>
        </div>
        <p className="surface-status">{copy.guidePage.status}</p>
      </header>

      <section className="surface-grid surface-grid--two-up">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.guidePage.quickStart.label}</p>
            <span className="panel-marker">{copy.guidePage.quickStart.marker}</span>
          </div>
          <ol className="guide-list">
            {copy.guidePage.quickStart.steps.map((step, index) => (
              <li className="guide-step" key={step.title}>
                <span className="guide-step__index">{String(index + 1).padStart(2, "0")}</span>
                <div className="guide-step__body">
                  <strong>{step.title}</strong>
                  <p>{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="inline-actions">
            <Link className="inline-action" to="/settings/llm">
              {copy.guidePage.actions.settings}
            </Link>
            <Link className="inline-action inline-action--primary" to="/runs/new">
              {copy.guidePage.actions.newRun}
            </Link>
          </div>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.guidePage.surfaces.label}</p>
            <span className="panel-marker">{copy.guidePage.surfaces.marker}</span>
          </div>
          <div className="list-stack">
            {copy.guidePage.surfaces.items.map((item) => (
              <div className="guide-surface" key={item.title}>
                <strong>{item.title}</strong>
                <p>{item.description}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.guidePage.graphTips.label}</p>
          <span className="panel-marker">{copy.guidePage.graphTips.marker}</span>
        </div>
        <ul className="guide-bullets">
          {copy.guidePage.graphTips.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <div className="inline-actions">
          <Link className="inline-action" to="/kg">
            {copy.guidePage.actions.knowledgeGraph}
          </Link>
        </div>
      </article>
    </section>
  );
}
