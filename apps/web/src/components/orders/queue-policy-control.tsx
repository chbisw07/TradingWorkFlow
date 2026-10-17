"use client";

import { useEffect, useState } from "react";
import { twfQueueApi, type QueuePolicy } from "../../lib/twf-queue";

export function QueuePolicyControl({ accountId }: { accountId: string }) {
  const [policy, setPolicy] = useState<QueuePolicy | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    if (accountId)
      void twfQueueApi<QueuePolicy>(`policy/${accountId}`)
        .then((value) => {
          if (current) {
            setPolicy(value);
            setError("");
          }
        })
        .catch((e: Error) => {
          if (current) setError(e.message);
        });
    return () => {
      current = false;
    };
  }, [accountId]);
  async function change(mode: "MANUAL" | "AUTO") {
    if (
      !policy ||
      policy.broker_account_id !== accountId ||
      busy ||
      mode === policy.current_dispatch_mode
    )
      return;
    const text =
      mode === "AUTO"
        ? "New Queue entries will use automatic dispatch. Existing Queue entries are unchanged."
        : "New Queue entries will require manual DISPATCH. Existing Queue entries are unchanged.";
    if (!window.confirm(text)) return;
    setBusy(true);
    try {
      setPolicy(
        await twfQueueApi<QueuePolicy>(`policy/${accountId}`, {
          current_dispatch_mode: mode,
          expected_version: policy.version,
        }),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const selected = policy?.broker_account_id === accountId ? policy : null;
  return (
    <div className="orders-queue-policy">
      <strong>Dispatch mode for new admissions</strong>
      {(["MANUAL", "AUTO"] as const).map((mode) => (
        <button
          key={mode}
          disabled={!selected || busy}
          aria-pressed={selected?.current_dispatch_mode === mode}
          onClick={() => void change(mode)}
        >
          {mode}
        </button>
      ))}
      <small>
        {selected?.current_dispatch_mode === "AUTO"
          ? "New Queue entries dispatch automatically after checks."
          : "New Queue entries wait for DISPATCH."}{" "}
        Existing Queue entries are unchanged.
      </small>
      {selected && !selected.execution_enabled && (
        <small>Queue execution is disabled by the operator.</small>
      )}
      {error && <span role="alert">{error}</span>}
    </div>
  );
}
