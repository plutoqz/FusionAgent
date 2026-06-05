import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { listValidationSessions } from "../../lib/api/client";
import { ValidationCaseResult, ValidationSessionRecord } from "../../lib/api/types";

function passRate(record: ValidationSessionRecord | null) {
  if (!record || record.summary.total_cases === 0) {
    return "0%";
  }
  return `${Math.round((record.summary.passed_cases / record.summary.total_cases) * 100)}%`;
}

function observedChildRunIds(result: ValidationCaseResult) {
  const value = result.observed?.child_run_ids;
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim() !== "") : [];
}

function failureReasons(result: ValidationCaseResult) {
  return Array.isArray(result.failure_reasons)
    ? result.failure_reasons.filter((item): item is string => typeof item === "string" && item.trim() !== "")
    : [];
}

function shortText(value: string | null | undefined, fallback = "—") {
  return value && value.trim() ? value : fallback;
}

export function ValidationSessionsPage() {
  const { copy } = useI18n();
  const [selectedSessionId, setSelectedSessionId] = useState("");

  const sessionsQuery = useQuery({
    queryKey: ["validation-sessions"],
    queryFn: listValidationSessions,
  });

  useEffect(() => {
    if (!selectedSessionId && sessionsQuery.data?.records.length) {
      setSelectedSessionId(sessionsQuery.data.records[0].session_id);
    }
  }, [selectedSessionId, sessionsQuery.data]);

  const selectedSession = useMemo(
    () => sessionsQuery.data?.records.find((record) => record.session_id === selectedSessionId) ?? null,
    [selectedSessionId, sessionsQuery.data],
  );
  const failedResults = selectedSession?.summary.results.filter((result) => !result.passed) ?? [];

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.validationPage.eyebrow}</p>
          <h1>{copy.validationPage.title}</h1>
        </div>
        <p className="surface-status">{copy.validationPage.status(sessionsQuery.data?.records.length ?? 0)}</p>
      </header>

      <section className="surface-grid surface-grid--two-up scenario-layout">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.validationPage.list.label}</p>
            <span className="panel-marker">{copy.validationPage.list.marker}</span>
          </div>

          {sessionsQuery.isLoading ? <p className="muted-text">{copy.validationPage.list.loading}</p> : null}
          {sessionsQuery.isError ? <p className="status-error">{copy.validationPage.list.error}</p> : null}
          {!sessionsQuery.isLoading && sessionsQuery.data?.records.length === 0 ? (
            <p className="muted-text">{copy.validationPage.list.empty}</p>
          ) : null}

          <div className="list-stack">
            {sessionsQuery.data?.records.map((record) => (
              <button
                key={record.session_id}
                className={record.session_id === selectedSessionId ? "run-row active run-row--stacked" : "run-row run-row--stacked"}
                type="button"
                onClick={() => setSelectedSessionId(record.session_id)}
              >
                <div className="run-row__main">
                  <strong>{record.session_id}</strong>
                  <span>{shortText(record.created_at)}</span>
                </div>
                <div className="run-row__meta run-row__meta--start">
                  <span>{record.summary.passed_cases} / {record.summary.total_cases}</span>
                  <span>{passRate(record)}</span>
                </div>
              </button>
            ))}
          </div>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.validationPage.summary.label}</p>
            <span className="panel-marker">{copy.validationPage.summary.marker}</span>
          </div>

          {selectedSession ? (
            <>
              <strong className="panel-state">{selectedSession.session_id}</strong>
              <dl className="status-list status-list--compact">
                <div>
                  <dt>{copy.validationPage.summary.items.passRate}</dt>
                  <dd>{passRate(selectedSession)}</dd>
                </div>
                <div>
                  <dt>{copy.validationPage.summary.items.passed}</dt>
                  <dd>{selectedSession.summary.passed_cases} / {selectedSession.summary.total_cases}</dd>
                </div>
                <div>
                  <dt>{copy.validationPage.summary.items.failed}</dt>
                  <dd>{selectedSession.summary.failed_cases}</dd>
                </div>
                <div>
                  <dt>{copy.validationPage.summary.items.matrix}</dt>
                  <dd>{selectedSession.summary.matrix_path}</dd>
                </div>
                <div>
                  <dt>{copy.validationPage.summary.items.createdAt}</dt>
                  <dd>{shortText(selectedSession.created_at)}</dd>
                </div>
                <div>
                  <dt>{copy.validationPage.summary.items.gitCommit}</dt>
                  <dd>{shortText(selectedSession.git_commit)}</dd>
                </div>
                <div>
                  <dt>{copy.validationPage.summary.items.outputRoot}</dt>
                  <dd>{selectedSession.summary.output_root}</dd>
                </div>
              </dl>
            </>
          ) : (
            <p className="muted-text">{copy.validationPage.summary.empty}</p>
          )}
        </article>
      </section>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.validationPage.failures.label}</p>
          <span className="panel-marker">{copy.validationPage.failures.marker}</span>
        </div>

        {selectedSession && failedResults.length === 0 ? (
          <p className="muted-text">{copy.validationPage.failures.empty}</p>
        ) : null}

        <div className="list-stack">
          {failedResults.map((result) => {
            const childRunIds = observedChildRunIds(result);
            const reasons = failureReasons(result);
            return (
              <div className="run-row run-row--stacked" key={result.case_id}>
                <div className="run-row__main">
                  <strong>{result.case_id}</strong>
                  <span>{result.phase}</span>
                </div>
                <dl className="status-list status-list--compact">
                  <div>
                    <dt>{copy.validationPage.failures.reasons}</dt>
                    <dd>{reasons.length ? reasons.join("; ") : shortText(result.error)}</dd>
                  </div>
                  <div>
                    <dt>{copy.validationPage.summary.items.matrix}</dt>
                    <dd>{shortText(result.summary_path)}</dd>
                  </div>
                </dl>
                <div className="inline-actions">
                  {result.scenario_id ? (
                    <Link className="inline-action" to="/scenarios">
                      {result.scenario_id}
                    </Link>
                  ) : null}
                  {childRunIds.map((runId) => (
                    <Link className="inline-action" key={runId} to={`/runs/${runId}`}>
                      {runId}
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </article>
    </section>
  );
}
