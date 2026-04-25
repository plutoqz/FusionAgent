import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { compareRuns } from "../../lib/api/client";
import { RunInspectionResponse } from "../../lib/api/types";
import { PhaseBadge } from "../../components/status/PhaseBadge";

function ComparePanel({ title, inspection }: { title: string; inspection: RunInspectionResponse | null }) {
  const { copy } = useI18n();

  return (
    <article className="surface-panel section-stack">
      <div className="panel-heading">
        <p className="panel-label">{title}</p>
        {inspection ? <PhaseBadge phase={inspection.run.phase} /> : <span className="panel-marker">{copy.runs.compare.panels.awaiting}</span>}
      </div>
      <strong className="panel-state">{inspection?.run.run_id ?? copy.runs.compare.panels.noRun}</strong>
      <p className="muted-text">{inspection?.run.trigger.content ?? copy.runs.compare.panels.providePair}</p>
      <dl className="status-list">
        <div>
          <dt>{copy.runs.compare.panels.jobType}</dt>
          <dd>{inspection?.run.job_type ? copy.runs.meta.jobTypes[inspection.run.job_type] : "-"}</dd>
        </div>
        <div>
          <dt>{copy.runs.compare.panels.workflow}</dt>
          <dd>{inspection?.plan?.workflow_id ?? "-"}</dd>
        </div>
        <div>
          <dt>{copy.runs.compare.panels.auditEvents}</dt>
          <dd>{inspection?.audit_events.length ?? 0}</dd>
        </div>
      </dl>
    </article>
  );
}

export function RunComparePage() {
  const { copy } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const [leftRunId, setLeftRunId] = useState(searchParams.get("left") ?? "");
  const [rightRunId, setRightRunId] = useState(searchParams.get("right") ?? "");

  const left = searchParams.get("left") ?? "";
  const right = searchParams.get("right") ?? "";

  const query = useQuery({
    queryKey: ["run-compare", left, right],
    queryFn: () => compareRuns(left, right),
    enabled: Boolean(left && right),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSearchParams({ left: leftRunId.trim(), right: rightRunId.trim() });
  }

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.runs.compare.eyebrow}</p>
          <h1>{copy.runs.compare.title}</h1>
        </div>
        <p className="surface-status">{copy.runs.compare.status}</p>
      </header>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.runs.compare.comparePair}</p>
          <span className="panel-marker">/runs/compare</span>
        </div>

        <form className="section-stack" onSubmit={handleSubmit}>
          <div className="field-row">
            <label className="field">
              <span>{copy.runs.compare.labels.leftRunId}</span>
              <input value={leftRunId} onChange={(event) => setLeftRunId(event.target.value)} />
            </label>
            <label className="field">
              <span>{copy.runs.compare.labels.rightRunId}</span>
              <input value={rightRunId} onChange={(event) => setRightRunId(event.target.value)} />
            </label>
          </div>
          <div className="inline-actions">
            <button className="inline-action inline-action--primary" type="submit">
              {copy.runs.compare.actions.loadComparison}
            </button>
          </div>
        </form>
      </article>

      <section className="surface-grid surface-grid--two-up">
        <ComparePanel title={copy.runs.compare.panels.left} inspection={query.data?.left ?? null} />
        <ComparePanel title={copy.runs.compare.panels.right} inspection={query.data?.right ?? null} />
      </section>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.runs.compare.differingDecisions}</p>
          <span className="panel-marker">{Object.keys(query.data?.differing_decisions ?? {}).length}</span>
        </div>

        {query.isLoading ? <p className="muted-text">{copy.runs.compare.loading}</p> : null}
        {query.isError ? <p className="status-error">{copy.runs.compare.error}</p> : null}

        {query.data && Object.keys(query.data.differing_decisions).length === 0 ? (
          <p className="muted-text">{copy.runs.compare.empty}</p>
        ) : null}

        <div className="list-stack">
          {Object.entries(query.data?.differing_decisions ?? {}).map(([decisionType, delta]) => (
            <div className="run-row" key={decisionType}>
              <div className="run-row__main">
                <strong>{decisionType}</strong>
                <span>{delta.left ?? "-"}</span>
              </div>
              <div className="run-row__meta">
                <span>{delta.right ?? "-"}</span>
              </div>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
