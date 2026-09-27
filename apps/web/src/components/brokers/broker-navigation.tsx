"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { Overview } from "../../lib/brokers";

const destinations = [
  ["overview", "/brokers", "Overview"],
  ["zerodha", "/brokers/zerodha", "Zerodha"],
  ["manage", "/brokers/manage", "Manage Brokers"],
] as const;

export function BrokerLinks({ active = "overview" }: { active?: string }) {
  return (
    <div className="broker-navigation">
      <nav
        className="broker-selector broker-tabs"
        aria-label="Broker workspace"
      >
        {destinations.map(([key, href, label]) => (
          <Link
            key={key}
            href={href}
            aria-current={active === key ? "page" : undefined}
          >
            {label}
          </Link>
        ))}
      </nav>
      <label className="broker-mobile-selector">
        Broker workspace
        <select
          value={
            destinations.find(([key]) => key === active)?.[1] ||
            "/brokers/development"
          }
          onChange={(event) => window.location.assign(event.target.value)}
        >
          {destinations.map(([key, href, label]) => (
            <option key={key} value={href}>
              {label}
            </option>
          ))}
          {active === "development" && (
            <option value="/brokers/development">
              Development / Synthetic
            </option>
          )}
        </select>
      </label>
      <DevelopmentNavigation />
    </div>
  );
}

function DevelopmentNavigation() {
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState<Overview["accounts"] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    fetch("/api/v1/brokers/overview", {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Unavailable");
        return response.json() as Promise<Overview>;
      })
      .then((value) => {
        if (!controller.signal.aborted) {
          setAccounts(value.accounts);
          setError(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [open]);
  return (
    <details
      className="broker-development"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>Development / Synthetic</summary>
      <nav aria-label="Development accounts">
        <Link href="/brokers/development">Synthetic overview</Link>
        {accounts?.map(({ account }) => (
          <Link
            key={account.broker_account_id}
            href={`/brokers/${account.broker_account_id}/dashboard`}
          >
            {account.label} <small>{account.mode}</small>
          </Link>
        ))}
        {open && !accounts && !error && <p role="status">Loading accounts…</p>}
        {error && (
          <p role="status">
            Accounts unavailable. Open the synthetic overview to retry.
          </p>
        )}
      </nav>
    </details>
  );
}
