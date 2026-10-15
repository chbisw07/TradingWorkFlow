"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BrokerReadTable } from "../brokers/broker-workspace";
import {
  brokerApi,
  readLabel,
  type Account,
  type Row,
  type Snapshot,
} from "../../lib/brokers";

/** Existing broker-ground-truth positions; TWF-managed Positions belong to OE-8. */
export function TradePositions({ account }: { account?: Account }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [now, setNow] = useState(0);
  useEffect(() => {
    const update = () => setNow(Date.now());
    const timer = window.setInterval(update, 5000);
    update();
    return () => window.clearInterval(timer);
  }, []);
  const accountId = account?.id;
  const generation = account?.generation;
  const state = account?.state;

  useEffect(() => {
    if (!accountId || state !== "connected") return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setLoading(true);
        setError("");
      }
    });
    void brokerApi<Snapshot>(
      `accounts/${accountId}/positions`,
      undefined,
      controller.signal,
    )
      .then(setSnapshot)
      .catch((failure: Error) => {
        if (failure.name !== "AbortError") setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [accountId, generation, state, refresh]);

  const current =
    snapshot &&
    snapshot.account.id === accountId &&
    snapshot.account.generation === generation
      ? snapshot
      : null;
  const rows: Row[] =
    current && Array.isArray(current.data) ? current.data : [];
  return (
    <section className="trade-positions orders-list" aria-label="Positions">
      <div className="orders-list-head">
        <div>
          <h2>Positions</h2>
          <p>
            Read-only positions from your selected Broker account. TWF-managed
            Positions are not available yet.
          </p>
        </div>
        <div className="trade-positions-actions">
          {account && (
            <Link href={`/brokers/accounts/${account.id}/positions`}>
              Open in Brokers
            </Link>
          )}
          <button
            type="button"
            disabled={!account || account.state !== "connected" || loading}
            onClick={() => setRefresh((value) => value + 1)}
          >
            Refresh
          </button>
        </div>
      </div>
      {!account ? (
        <p className="orders-empty">
          Connect a Broker account to view its positions.
        </p>
      ) : account.state !== "connected" ? (
        <p className="broker-notice">
          This account needs a connection before positions can be read.
        </p>
      ) : (
        <>
          <p className="trade-positions-status">
            {readLabel(account, current, !!error, now)}
          </p>
          {error && (
            <p className="broker-notice" role="alert">
              {error} Retained data may be out of date.
            </p>
          )}
          {loading && <p role="status">Loading positions…</p>}
          {current && <BrokerReadTable view="positions" rows={rows} />}
          {current && (
            <p className="orders-list-note">
              Read at {new Date(current.fetched_at).toLocaleString()} ·
              On-demand Broker snapshot · INR
            </p>
          )}
        </>
      )}
    </section>
  );
}
