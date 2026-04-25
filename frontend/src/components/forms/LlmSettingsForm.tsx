import { FormEvent, useEffect, useState } from "react";

import { useI18n } from "../../app/i18n";
import { LlmSettingsResponse, LlmSettingsUpdateRequest } from "../../lib/api/types";

type LlmSettingsFormProps = {
  initialSettings: LlmSettingsResponse;
  onValidate: (payload: LlmSettingsUpdateRequest) => Promise<void>;
  onSave: (payload: LlmSettingsUpdateRequest) => Promise<void>;
  isValidating: boolean;
  isSaving: boolean;
};

export function LlmSettingsForm({
  initialSettings,
  onValidate,
  onSave,
  isValidating,
  isSaving,
}: LlmSettingsFormProps) {
  const { copy } = useI18n();
  const [provider, setProvider] = useState(initialSettings.provider ?? "auto");
  const [baseUrl, setBaseUrl] = useState(initialSettings.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(initialSettings.model ?? "");
  const [timeoutSec, setTimeoutSec] = useState(String(initialSettings.timeout_sec ?? 60));

  useEffect(() => {
    setProvider(initialSettings.provider ?? "auto");
    setBaseUrl(initialSettings.base_url ?? "");
    setModel(initialSettings.model ?? "");
    setTimeoutSec(String(initialSettings.timeout_sec ?? 60));
  }, [initialSettings]);

  function buildPayload(): LlmSettingsUpdateRequest {
    return {
      provider,
      base_url: baseUrl || null,
      api_key: apiKey,
      model: model || null,
      timeout_sec: timeoutSec ? Number(timeoutSec) : null,
    };
  }

  async function handleValidate(event: FormEvent<HTMLButtonElement>) {
    event.preventDefault();
    await onValidate(buildPayload());
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave(buildPayload());
  }

  return (
    <form className="section-stack" onSubmit={handleSubmit}>
      <label className="field">
        <span>{copy.settingsPage.form.labels.provider}</span>
        <select value={provider} onChange={(event) => setProvider(event.target.value)}>
          <option value="auto">{copy.settingsPage.providers.auto}</option>
          <option value="mock">{copy.settingsPage.providers.mock}</option>
          <option value="openai">{copy.settingsPage.providers.openai}</option>
        </select>
      </label>

      <label className="field">
        <span>{copy.settingsPage.form.labels.baseUrl}</span>
        <input
          aria-label={copy.settingsPage.form.labels.baseUrl}
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
        />
      </label>

      <label className="field">
        <span>{copy.settingsPage.form.labels.apiKey}</span>
        <input
          aria-label={copy.settingsPage.form.labels.apiKey}
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={initialSettings.api_key_masked ?? ""}
        />
      </label>

      <label className="field">
        <span>{copy.settingsPage.form.labels.model}</span>
        <input value={model} onChange={(event) => setModel(event.target.value)} />
      </label>

      <label className="field">
        <span>{copy.settingsPage.form.labels.timeout}</span>
        <input type="number" min="1" value={timeoutSec} onChange={(event) => setTimeoutSec(event.target.value)} />
      </label>

      <p className="muted-text">
        {initialSettings.has_api_key && initialSettings.api_key_masked
          ? copy.settingsPage.form.helper.masked(initialSettings.api_key_masked)
          : copy.settingsPage.form.helper.empty}
      </p>

      <div className="inline-actions">
        <button className="inline-action" type="button" onClick={handleValidate} disabled={isValidating}>
          {isValidating ? copy.settingsPage.form.actions.validating : copy.settingsPage.form.actions.validate}
        </button>
        <button className="inline-action inline-action--primary" type="submit" disabled={isSaving}>
          {isSaving ? copy.settingsPage.form.actions.saving : copy.settingsPage.form.actions.save}
        </button>
      </div>
    </form>
  );
}
