import { FormEvent, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { listRuns } from "../../lib/api/client";
import { JobType, RunListRecord, RunPhase } from "../../lib/api/types";
import { PhaseBadge } from "../../components/status/PhaseBadge";

const jobTypes: Array<JobType | ""> = ["", "building", "road", "water", "poi"];
const quickPhases: RunPhase[] = ["queued", "running", "succeeded", "failed"];

function sortRuns(records: RunListRecord[]) {
  return [...records].sort((left, right) => {
    const leftValue = new Date(left.updated_at ?? left.created_at ?? 0).getTime();
    const rightValue = new Date(right.updated_at ?? right.created_at ?? 0).getTime();
    return rightValue - leftValue;
  });
}

export function RunsPage() {
  const { copy } = useI18n();
  const navigate = useNavigate();
  const [phase, setPhase] = useState("");
  const [jobType, setJobType] = useState<JobType | "">("");
  const [leftRunId, setLeftRunId] = useState("");
  const [rightRunId, setRightRunId] = useState("");

  const query = useQuery({
    queryKey: ["runs", phase, jobType],
    queryFn: () =>
      listRuns({
        phase: phase || undefined,
        jobType: jobType || undefined,
      }),
  });

  const records = useMemo(() => sortRuns(query.data?.records ?? []), [query.data?.records]);

  function handleCompareSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!leftRunId.trim() || !rightRunId.trim()) {
      return;
    }
    navigate(`/runs/compare?left=${encodeURIComponent(leftRunId.trim())}&right=${encodeURIComponent(rightRunId.trim())}`);
  }

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.runs.list.eyebrow}</p>
          <h1>{copy.runs.list.title}</h1>
        </div>
        <p className="surface-status">{copy.runs.list.recordsInScope(records.length)}</p>
      </header>

      <section className="surface-grid surface-grid--two-up">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.list.filters}</p>
            <span className="panel-marker">{copy.runs.list.registry}</span>
          </div>
          <div className="chip-row" role="group" aria-label={copy.runs.list.quickFilters}>
            {quickPhases.map((item) => (
              <button
                key={item}
                className={phase === item ? "filter-chip active" : "filter-chip"}
                type="button"
                onClick={() => setPhase((current) => (current === item ? "" : item))}
              >
                {copy.runs.meta.phases[item]}
              </button>
            ))}
          </div>
          <div className="field-row">
            <label className="field">
              <span>{copy.runs.list.labels.phase}</span>
              <input value={phase} onChange={(event) => setPhase(event.target.value)} placeholder={copy.runs.list.placeholders.phase} />
            </label>
            <label className="field">
              <span>{copy.runs.list.labels.jobType}</span>
              <select value={jobType} onChange={(event) => setJobType(event.target.value as JobType | "")}>
                {jobTypes.map((item) => (
                  <option key={item || "all"} value={item}>
                    {item ? copy.runs.meta.jobTypes[item] : copy.runs.list.all}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="inline-actions">
            <Link className="inline-action" to="/runs/new">
              {copy.runs.list.actions.newTask}
            </Link>
          </div>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.list.compareLane}</p>
            <span className="panel-marker">{copy.runs.list.sideBySide}</span>
          </div>
          <p className="muted-text">{copy.runs.list.compareHint}</p>
          <form className="section-stack" onSubmit={handleCompareSubmit}>
            <div className="field-row">
              <label className="field">
                <span>{copy.runs.list.labels.leftRunId}</span>
                <input value={leftRunId} onChange={(event) => setLeftRunId(event.target.value)} />
              </label>
              <label className="field">
                <span>{copy.runs.list.labels.rightRunId}</span>
                <input value={rightRunId} onChange={(event) => setRightRunId(event.target.value)} />
              </label>
            </div>
            <div className="inline-actions">
              <button className="inline-action inline-action--primary" type="submit">
                {copy.runs.list.actions.compareRuns}
              </button>
            </div>
          </form>
        </article>
      </section>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.runs.list.recentRuns}</p>
          <span className="panel-marker">/api/v2/runs</span>
        </div>

        {query.isLoading ? <p className="muted-text">{copy.runs.list.loading}</p> : null}
        {query.isError ? <p className="status-error">{copy.runs.list.error}</p> : null}
        {!query.isLoading && records.length === 0 ? <p className="muted-text">{copy.runs.list.empty}</p> : null}

        <div className="list-stack">
          {records.map((record) => (
            <Link className="run-row run-row--stacked" key={record.run_id} to={`/runs/${record.run_id}`}>
              <div className="run-row__main">
                <strong>{record.run_id}</strong>
                <span>{record.trigger?.content ?? copy.runs.list.noTrigger}</span>
              </div>
              <div className="run-row__meta run-row__meta--start">
                <PhaseBadge phase={record.phase} />
                <span>{copy.runs.meta.jobTypes[record.job_type]}</span>
                <span>
                  {record.created_at ?? copy.runs.list.persistedRun}
                  {typeof record.progress === "number" ? ` · ${record.progress}%` : ""}
                </span>
              </div>
            </Link>
          ))}
        </div>
      </article>
    </section>
  );
}
