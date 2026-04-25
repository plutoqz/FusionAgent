import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useI18n } from "../../app/i18n";
import { ApiError, createRun } from "../../lib/api/client";
import { CreateRunPayload, JobType } from "../../lib/api/types";

const jobTypes: JobType[] = ["building", "road", "water", "poi"];

export function RunCreatePage() {
  const { copy } = useI18n();
  const navigate = useNavigate();
  const [jobType, setJobType] = useState<JobType>("building");
  const [inputStrategy, setInputStrategy] = useState<CreateRunPayload["inputStrategy"]>("uploaded");
  const [triggerType, setTriggerType] = useState("user_query");
  const [triggerContent, setTriggerContent] = useState(copy.runs.create.defaults.triggerContent);
  const [disasterType, setDisasterType] = useState("");
  const [spatialExtent, setSpatialExtent] = useState("");
  const [temporalStart, setTemporalStart] = useState("");
  const [temporalEnd, setTemporalEnd] = useState("");
  const [targetCrs, setTargetCrs] = useState("");
  const [debug, setDebug] = useState(false);
  const [osmZip, setOsmZip] = useState<File | null>(null);
  const [refZip, setRefZip] = useState<File | null>(null);

  const mutation = useMutation({
    mutationFn: createRun,
    onSuccess: (result) => {
      navigate(`/runs/${result.run_id}`);
    },
  });

  const errorMessage = useMemo(() => {
    if (!(mutation.error instanceof ApiError)) {
      return mutation.error instanceof Error ? mutation.error.message : null;
    }
    return mutation.error.message;
  }, [mutation.error]);

  useEffect(() => {
    if (triggerContent === "manual trigger" || triggerContent === "手动触发") {
      setTriggerContent(copy.runs.create.defaults.triggerContent);
    }
  }, [copy.runs.create.defaults.triggerContent, triggerContent]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({
      jobType,
      triggerType,
      triggerContent,
      disasterType,
      spatialExtent,
      temporalStart,
      temporalEnd,
      targetCrs,
      debug,
      inputStrategy,
      osmZip,
      refZip,
    });
  }

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.runs.create.eyebrow}</p>
          <h1>{copy.runs.create.title}</h1>
        </div>
        <p className="surface-status">{copy.runs.create.status}</p>
      </header>

      <form className="surface-grid surface-grid--two-up" onSubmit={handleSubmit}>
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.create.coreRequest}</p>
            <span className="panel-marker">{copy.runs.create.submissionRoute}</span>
          </div>

          <label className="field">
            <span>{copy.runs.create.labels.jobType}</span>
            <select value={jobType} onChange={(event) => setJobType(event.target.value as JobType)}>
              {jobTypes.map((item) => (
                <option key={item} value={item}>
                  {copy.runs.meta.jobTypes[item]}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>{copy.runs.create.labels.inputStrategy}</span>
            <select
              value={inputStrategy}
              onChange={(event) =>
                setInputStrategy(event.target.value as CreateRunPayload["inputStrategy"])
              }
            >
              <option value="uploaded">{copy.runs.meta.inputStrategies.uploaded}</option>
              <option value="task_driven_auto">{copy.runs.meta.inputStrategies.task_driven_auto}</option>
            </select>
          </label>

          <label className="field">
            <span>{copy.runs.create.labels.triggerType}</span>
            <select value={triggerType} onChange={(event) => setTriggerType(event.target.value)}>
              <option value="user_query">{copy.runs.meta.triggerTypes.user_query}</option>
              <option value="disaster_event">{copy.runs.meta.triggerTypes.disaster_event}</option>
              <option value="scheduled">{copy.runs.meta.triggerTypes.scheduled}</option>
            </select>
          </label>

          <label className="field">
            <span>{copy.runs.create.labels.triggerContent}</span>
            <textarea
              rows={4}
              value={triggerContent}
              onChange={(event) => setTriggerContent(event.target.value)}
            />
          </label>

          <div className="field-row">
            <label className="field">
              <span>{copy.runs.create.labels.disasterType}</span>
              <input value={disasterType} onChange={(event) => setDisasterType(event.target.value)} />
            </label>
            <label className="field">
              <span>{copy.runs.create.labels.targetCrs}</span>
              <input value={targetCrs} onChange={(event) => setTargetCrs(event.target.value)} />
            </label>
          </div>

          <label className="toggle-field">
            <input
              type="checkbox"
              checked={debug}
              onChange={(event) => setDebug(event.target.checked)}
            />
            <span>{copy.runs.create.labels.debug}</span>
          </label>
        </article>

        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.runs.create.spatialContext}</p>
            <span className="panel-marker">{copy.runs.meta.inputStrategies[inputStrategy]}</span>
          </div>

          <div className="field-row">
            <label className="field">
              <span>{copy.runs.create.labels.spatialExtent}</span>
              <input value={spatialExtent} onChange={(event) => setSpatialExtent(event.target.value)} />
            </label>
            <label className="field">
              <span>{copy.runs.create.labels.temporalStart}</span>
              <input value={temporalStart} onChange={(event) => setTemporalStart(event.target.value)} />
            </label>
            <label className="field">
              <span>{copy.runs.create.labels.temporalEnd}</span>
              <input value={temporalEnd} onChange={(event) => setTemporalEnd(event.target.value)} />
            </label>
          </div>

          {inputStrategy === "uploaded" ? (
            <>
              <label className="field">
                <span>{copy.runs.create.labels.osmZip}</span>
                <input
                  type="file"
                  accept=".zip"
                  onChange={(event) => setOsmZip(event.target.files?.[0] ?? null)}
                />
              </label>
              <label className="field">
                <span>{copy.runs.create.labels.refZip}</span>
                <input
                  type="file"
                  accept=".zip"
                  onChange={(event) => setRefZip(event.target.files?.[0] ?? null)}
                />
              </label>
            </>
          ) : (
            <div className="empty-panel">
              <strong>{copy.runs.create.taskDriven.title}</strong>
              <p>{copy.runs.create.taskDriven.description}</p>
            </div>
          )}

          {errorMessage ? <p className="status-error">{errorMessage}</p> : null}
          {mutation.isSuccess ? <p className="status-success">{copy.runs.create.statusCopy.redirecting}</p> : null}

          <div className="inline-actions">
            <button className="inline-action inline-action--primary" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? copy.runs.create.statusCopy.submitting : copy.runs.create.statusCopy.submit}
            </button>
          </div>
        </article>
      </form>
    </section>
  );
}
