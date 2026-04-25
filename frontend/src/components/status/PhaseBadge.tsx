import { useI18n } from "../../app/i18n";
import { RunPhase } from "../../lib/api/types";

type PhaseBadgeProps = {
  phase: RunPhase | string;
};

export function PhaseBadge({ phase }: PhaseBadgeProps) {
  const { copy } = useI18n();
  const normalized = phase.toLowerCase();
  const translated =
    normalized in copy.runs.meta.phases
      ? copy.runs.meta.phases[normalized as keyof typeof copy.runs.meta.phases]
      : normalized.replace(/_/g, " ");

  return <span className={`phase-badge phase-badge--${normalized}`}>{translated}</span>;
}
