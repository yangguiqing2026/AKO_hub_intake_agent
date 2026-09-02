const STEPS = ["PARSING", "AMBIGUITY_DETECTED", "CLARIFYING", "FORM_BUILDING", "VALIDATING", "REVIEWING", "TERMINAL"] as const;
const TERMINAL = ["DELIVERED", "QUEUED_LOCAL", "MANUAL_REVIEW", "FAILED", "ABANDONED"] as const;

function indexOf(status: string): number {
  if (TERMINAL.includes(status as (typeof TERMINAL)[number])) return STEPS.length - 1;
  const i = STEPS.indexOf(status as (typeof STEPS)[number]);
  return i === -1 ? 0 : i;
}

export function ProgressStepper({ status }: { status: string }): JSX.Element | null {
  const idx = indexOf(status);
  if (status === "IDLE") return null;
  return (
    <ol style={{ display: "flex", gap: 4, listStyle: "none", padding: 0, margin: "12px 0" }}>
      {STEPS.map((s, i) => (
        <li key={s} style={{ flex: 1, height: 6, borderRadius: 3, background: i <= idx ? "var(--c-gold)" : "var(--c-border)" }} title={s} />
      ))}
    </ol>
  );
}
