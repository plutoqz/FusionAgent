import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { createScenarioRun, getScenarioDocument, listScenarioDocuments, listScenarioRuns } from "../../lib/api/client";
import { JobType, ScenarioDocumentEntry } from "../../lib/api/types";
import { PhaseBadge } from "../../components/status/PhaseBadge";

const jobTypes: JobType[] = ["building", "road", "water", "poi"];

function reportTabLabel(copy: ReturnType<typeof useI18n>["copy"], document: ScenarioDocumentEntry) {
  if (document.language === "zh") {
    return copy.scenarioPage.reports.tabs.zh;
  }
  if (document.language === "en") {
    return copy.scenarioPage.reports.tabs.en;
  }
  return document.filename;
}

export function ScenarioPage() {
  const { copy } = useI18n();
  const [scenarioName, setScenarioName] = useState(copy.scenarioPage.defaults.scenarioName);
  const [triggerContent, setTriggerContent] = useState(copy.scenarioPage.defaults.triggerContent);
  const [disasterType, setDisasterType] = useState("");
  const [targetCrs, setTargetCrs] = useState("");
  const [debug, setDebug] = useState(false);
  const [selectedJobTypes, setSelectedJobTypes] = useState<JobType[]>(["building", "road"]);
  const [selectedScenarioId, setSelectedScenarioId] = useState("");
  const [selectedDocument, setSelectedDocument] = useState("");

  const scenarioQuery = useQuery({
    queryKey: ["scenario-runs"],
    queryFn: listScenarioRuns,
  });

  useEffect(() => {
    if (!selectedScenarioId && scenarioQuery.data?.records.length) {
      setSelectedScenarioId(scenarioQuery.data.records[0].scenario_id);
    }
  }, [scenarioQuery.data, selectedScenarioId]);

  const documentsQuery = useQuery({
    queryKey: ["scenario-documents", selectedScenarioId],
    queryFn: () => listScenarioDocuments(selectedScenarioId),
    enabled: Boolean(selectedScenarioId),
  });

  useEffect(() => {
    if (!documentsQuery.data?.documents.length) {
      return;
    }
    const preferred =
      documentsQuery.data.documents.find((item) => item.language === "zh") ??
      documentsQuery.data.documents[0];

    if (!selectedDocument) {
      setSelectedDocument(preferred.filename);
    }
  }, [documentsQuery.data, selectedDocument]);

  const documentQuery = useQuery({
    queryKey: ["scenario-document", selectedScenarioId, selectedDocument],
    queryFn: () => getScenarioDocument(selectedScenarioId, selectedDocument),
    enabled: Boolean(selectedScenarioId && selectedDocument),
  });

  const createScenarioMutation = useMutation({
    mutationFn: createScenarioRun,
    onSuccess: (result) => {
      setSelectedScenarioId(result.scenario_id);
      setSelectedDocument("");
    },
  });

  const selectedScenario = useMemo(
    () => scenarioQuery.data?.records.find((item) => item.scenario_id === selectedScenarioId) ?? null,
    [scenarioQuery.data, selectedScenarioId],
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createScenarioMutation.mutate({
      scenario_name: scenarioName,
      trigger_content: triggerContent,
      disaster_type: disasterType || undefined,
      job_types: selectedJobTypes,
      target_crs: targetCrs || undefined,
      debug,
    });
  }

  function toggleJobType(jobType: JobType) {
    setSelectedJobTypes((current) =>
      current.includes(jobType) ? current.filter((item) => item !== jobType) : [...current, jobType],
    );
  }

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.scenarioPage.eyebrow}</p>
          <h1>{copy.scenarioPage.title}</h1>
        </div>
        <p className="surface-status">{copy.scenarioPage.status(scenarioQuery.data?.records.length ?? 0)}</p>
      </header>

      <section className="surface-grid surface-grid--two-up scenario-layout">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.scenarioPage.recent.label}</p>
            <span className="panel-marker">{copy.scenarioPage.recent.marker}</span>
          </div>

          {scenarioQuery.isLoading ? <p className="muted-text">{copy.scenarioPage.recent.loading}</p> : null}
          {scenarioQuery.isError ? <p className="status-error">{copy.scenarioPage.recent.error}</p> : null}
          {!scenarioQuery.isLoading && scenarioQuery.data?.records.length === 0 ? (
            <p className="muted-text">{copy.scenarioPage.recent.empty}</p>
          ) : null}

          <div className="list-stack">
            {scenarioQuery.data?.records.map((record) => (
              <button
                key={record.scenario_id}
                className={record.scenario_id === selectedScenarioId ? "run-row active run-row--stacked" : "run-row run-row--stacked"}
                type="button"
                onClick={() => {
                  setSelectedScenarioId(record.scenario_id);
                  setSelectedDocument("");
                }}
              >
                <div className="run-row__main">
                  <strong>{record.scenario_name ?? record.scenario_id}</strong>
                  <span>{record.scenario_id}</span>
                </div>
                <div className="run-row__meta run-row__meta--start">
                  <PhaseBadge phase={record.phase} />
                  <span>{copy.scenarioPage.recent.childRuns(record.child_run_ids?.length ?? 0)}</span>
                </div>
              </button>
            ))}
          </div>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.scenarioPage.overview.label}</p>
            <span className="panel-marker">{copy.scenarioPage.overview.marker}</span>
          </div>

          {selectedScenario ? (
            <>
              <strong className="panel-state">{selectedScenario.scenario_name ?? selectedScenario.scenario_id}</strong>
              <dl className="status-list status-list--compact">
                <div>
                  <dt>{copy.scenarioPage.overview.items.scenarioId}</dt>
                  <dd>{selectedScenario.scenario_id}</dd>
                </div>
                <div>
                  <dt>{copy.scenarioPage.overview.items.phase}</dt>
                  <dd>{selectedScenario.phase}</dd>
                </div>
                <div>
                  <dt>{copy.scenarioPage.overview.items.reports}</dt>
                  <dd>{documentsQuery.data?.documents.length ?? 0}</dd>
                </div>
              </dl>
              <div className="chip-row">
                {(selectedScenario.child_run_ids ?? []).length ? (
                  selectedScenario.child_run_ids?.map((childRunId) => (
                    <Link className="filter-chip filter-chip--link" key={childRunId} to={`/runs/${childRunId}`}>
                      {childRunId}
                    </Link>
                  ))
                ) : (
                  <span className="muted-text">{copy.scenarioPage.overview.noChildRuns}</span>
                )}
              </div>
            </>
          ) : (
            <p className="muted-text">{copy.scenarioPage.overview.empty}</p>
          )}
        </article>
      </section>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.scenarioPage.reports.label}</p>
          <span className="panel-marker">{copy.scenarioPage.reports.marker}</span>
        </div>

        {documentsQuery.isLoading ? <p className="muted-text">{copy.scenarioPage.reports.loadingList}</p> : null}
        {documentsQuery.isError ? <p className="status-error">{copy.scenarioPage.reports.error}</p> : null}
        {documentsQuery.data && documentsQuery.data.documents.length === 0 ? (
          <p className="muted-text">{copy.scenarioPage.reports.empty}</p>
        ) : null}

        {documentsQuery.data?.documents.length ? (
          <div className="report-tabs" role="tablist" aria-label={copy.scenarioPage.reports.label}>
            {documentsQuery.data.documents.map((document) => (
              <button
                key={document.filename}
                className={document.filename === selectedDocument ? "report-tab active" : "report-tab"}
                role="tab"
                type="button"
                aria-selected={document.filename === selectedDocument}
                onClick={() => setSelectedDocument(document.filename)}
              >
                {reportTabLabel(copy, document)}
              </button>
            ))}
          </div>
        ) : null}

        {documentQuery.isLoading ? <p className="muted-text">{copy.scenarioPage.reports.loadingContent}</p> : null}
        {documentQuery.data ? (
          <article className="markdown-surface">
            <ReactMarkdown>{documentQuery.data.content}</ReactMarkdown>
          </article>
        ) : null}
      </article>

      <article className="surface-panel section-stack">
        <div className="panel-heading">
          <p className="panel-label">{copy.scenarioPage.form.label}</p>
          <span className="panel-marker">{copy.scenarioPage.form.marker}</span>
        </div>
        <p className="muted-text">{copy.scenarioPage.form.helper}</p>

        <form className="section-stack" onSubmit={handleSubmit}>
          <label className="field">
            <span>{copy.scenarioPage.form.labels.scenarioName}</span>
            <input
              aria-label={copy.scenarioPage.form.labels.scenarioName}
              value={scenarioName}
              onChange={(event) => setScenarioName(event.target.value)}
            />
          </label>

          <label className="field">
            <span>{copy.scenarioPage.form.labels.triggerContent}</span>
            <textarea
              rows={4}
              value={triggerContent}
              onChange={(event) => setTriggerContent(event.target.value)}
            />
          </label>

          <div className="field-row">
            <label className="field">
              <span>{copy.scenarioPage.form.labels.disasterType}</span>
              <input value={disasterType} onChange={(event) => setDisasterType(event.target.value)} />
            </label>
            <label className="field">
              <span>{copy.scenarioPage.form.labels.targetCrs}</span>
              <input value={targetCrs} onChange={(event) => setTargetCrs(event.target.value)} />
            </label>
          </div>

          <div className="field">
            <span>{copy.scenarioPage.form.labels.jobTypes}</span>
            <div className="checkbox-grid">
              {jobTypes.map((jobType) => (
                <label className="checkbox-chip" key={jobType}>
                  <input
                    type="checkbox"
                    checked={selectedJobTypes.includes(jobType)}
                    onChange={() => toggleJobType(jobType)}
                  />
                  <span>{copy.runs.meta.jobTypes[jobType]}</span>
                </label>
              ))}
            </div>
          </div>

          <label className="toggle-field">
            <input type="checkbox" checked={debug} onChange={(event) => setDebug(event.target.checked)} />
            <span>{copy.scenarioPage.form.labels.debug}</span>
          </label>

          <div className="inline-actions">
            <button className="inline-action inline-action--primary" type="submit">
              {createScenarioMutation.isPending
                ? copy.scenarioPage.form.actions.submitting
                : copy.scenarioPage.form.actions.submit}
            </button>
          </div>
        </form>
      </article>
    </section>
  );
}
