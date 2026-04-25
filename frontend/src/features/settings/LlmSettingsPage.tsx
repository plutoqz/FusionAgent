import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useI18n } from "../../app/i18n";
import { LlmSettingsForm } from "../../components/forms/LlmSettingsForm";
import { getLlmSettings, updateLlmSettings, validateLlmSettings } from "../../lib/api/client";

export function LlmSettingsPage() {
  const { copy } = useI18n();
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["llm-settings"],
    queryFn: getLlmSettings,
  });

  const validateMutation = useMutation({
    mutationFn: validateLlmSettings,
    onSuccess: () => {
      setFeedback(copy.settingsPage.state.validateSuccess);
    },
  });

  const saveMutation = useMutation({
    mutationFn: updateLlmSettings,
    onSuccess: (result) => {
      queryClient.setQueryData(["llm-settings"], result);
      setFeedback(copy.settingsPage.state.saveSuccess);
    },
  });

  return (
    <section className="surface-page">
      <header className="surface-header">
        <div>
          <p className="surface-eyebrow">{copy.settingsPage.eyebrow}</p>
          <h1>{copy.settingsPage.title}</h1>
        </div>
        <p className="surface-status">{copy.settingsPage.status}</p>
      </header>

      <section className="surface-grid surface-grid--two-up">
        <article className="surface-panel section-stack">
          <div className="panel-heading">
            <p className="panel-label">{copy.settingsPage.form.label}</p>
            <span className="panel-marker">{copy.settingsPage.form.marker}</span>
          </div>

          {settingsQuery.isLoading ? <p className="muted-text">{copy.settingsPage.state.loading}</p> : null}
          {settingsQuery.isError ? <p className="status-error">{copy.settingsPage.state.loadError}</p> : null}
          {saveMutation.isError ? (
            <p className="status-error">{saveMutation.error instanceof Error ? saveMutation.error.message : copy.settingsPage.state.loadError}</p>
          ) : null}
          {validateMutation.isError ? (
            <p className="status-error">{validateMutation.error instanceof Error ? validateMutation.error.message : copy.settingsPage.state.loadError}</p>
          ) : null}
          {feedback ? <p className="status-success">{feedback}</p> : null}

          {settingsQuery.data ? (
            <LlmSettingsForm
              initialSettings={settingsQuery.data}
              isSaving={saveMutation.isPending}
              isValidating={validateMutation.isPending}
              onSave={async (payload) => {
                setFeedback(null);
                await saveMutation.mutateAsync(payload);
              }}
              onValidate={async (payload) => {
                setFeedback(null);
                await validateMutation.mutateAsync(payload);
              }}
            />
          ) : null}
        </article>
      </section>
    </section>
  );
}
