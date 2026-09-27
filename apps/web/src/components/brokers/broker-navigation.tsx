"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { connectionHref, connectionName } from "../../lib/broker-connections";
import { useBrokerSession } from "./broker-session";
import { useEffect, useState } from "react";
import type { Overview } from "../../lib/brokers";

export function BrokerLinks() {
  const { connections, development } = useBrokerSession();
  const pathname = usePathname();
  const destinations = [
    {
      href: "/brokers",
      label: "Overview",
      active: pathname === "/brokers" || pathname === "/brokers/zerodha",
    },
    ...(connections || []).flatMap((value) => {
      const href = connectionHref(value);
      return href
        ? [
            {
              href,
              label: connectionName(value),
              active:
                pathname.includes(value.account.broker_account_id) &&
                !pathname.startsWith("/brokers/manage"),
            },
          ]
        : [];
    }),
    {
      href: "/brokers/manage",
      label: "Manage Brokers",
      active: pathname.startsWith("/brokers/manage"),
    },
  ];
  return (
    <div className="broker-navigation">
      <nav
        className="broker-selector broker-tabs"
        aria-label="Broker workspace"
      >
        {destinations.map(({ href, label, active }) => (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
          >
            {label}
          </Link>
        ))}
      </nav>
      <label className="broker-mobile-selector">
        Broker workspace
        <select
          value={destinations.find((item) => item.active)?.href || ""}
          onChange={(event) => window.location.assign(event.target.value)}
        >
          {!destinations.some((item) => item.active) && (
            <option value="" disabled>
              Select a broker
            </option>
          )}
          {destinations.map(({ href, label }) => (
            <option key={href} value={href}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {development && <DevelopmentNavigation />}
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
