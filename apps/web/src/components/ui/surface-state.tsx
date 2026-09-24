import type { ReactNode } from "react";

export const stateLabels = {
  LOADING: "Loading",
  EMPTY: "Empty",
  READY: "Ready",
  STALE: "Stale",
  UNAVAILABLE: "Unavailable",
  ERROR: "Error",
  DISCONNECTED: "Disconnected",
  COMING_SOON: "Coming soon",
} as const;

export type SurfaceStateKind = keyof typeof stateLabels;

export function StateBadge({
  state,
  label,
}: {
  state: SurfaceStateKind;
  label?: string;
}) {
  return (
    <span className="state-badge" data-state={state}>
      <span className="state-dot" aria-hidden="true" />
      {label ?? stateLabels[state]}
    </span>
  );
}

export function SurfaceState({
  state,
  title,
  description,
  action,
  headingLevel = 3,
}: {
  state: SurfaceStateKind;
  title: string;
  description: string;
  action?: ReactNode;
  headingLevel?: 1 | 2 | 3 | 4 | 5 | 6;
}) {
  const Heading = `h${headingLevel}` as const;
  return (
    <div
      className="surface-state"
      data-state={state}
      role={state === "ERROR" ? "alert" : "status"}
      aria-busy={state === "LOADING"}
    >
      <StateBadge state={state} />
      <Heading className="surface-state-title">{title}</Heading>
      <p>{description}</p>
      {action && <div className="state-action">{action}</div>}
    </div>
  );
}
