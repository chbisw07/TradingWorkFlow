"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../shell/icon";
import {
  twfQueueApi,
  TWFQueueApiError,
  type TWFQueueEntry,
  type TWFQueueEvent,
  type TWFQueuePage,
} from "../../lib/twf-queue";

type QueueTab = "Overview" | "TWF Order" | "Queue History";

function displayDate(value: string) {
  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function displayAge(value: string) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(value).getTime()) / 60000),
  );
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return hours < 24
    ? `${hours}h ${minutes % 60}m`
    : `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

export function QueueWorkspace({
  selectedId,
  onSelect,
  onViewOrder,
  refreshKey,
}: {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onViewOrder: (id: string) => void;
  refreshKey: number;
}) {
  const [entries, setEntries] = useState<TWFQueueEntry[]>([]);
  const requestEpoch = useRef(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [stateFilter, setStateFilter] = useState<"ALL" | "READY" | "HELD">(
    "ALL",
  );
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [detail, setDetail] = useState<TWFQueueEntry | null>(null);
  const [history, setHistory] = useState<TWFQueueEvent[]>([]);
  const [tab, setTab] = useState<QueueTab>("Overview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = useCallback(
    async (notice = "") => {
      const epoch = ++requestEpoch.current;
      try {
        const query = new URLSearchParams({ limit: "50" });
        if (stateFilter !== "ALL") query.set("state", stateFilter);
        const page = await twfQueueApi<TWFQueuePage>(`?${query}`);
        if (epoch !== requestEpoch.current) return;
        setEntries(page.items);
        setNextCursor(page.next_cursor);
        setError(notice);
      } catch (e) {
        if (epoch === requestEpoch.current) setError((e as Error).message);
      } finally {
        if (epoch === requestEpoch.current) setLoading(false);
      }
    },
    [stateFilter],
  );
  useEffect(() => {
    void Promise.resolve().then(() => refresh());
  }, [refresh, refreshKey]);
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    void Promise.all([
      twfQueueApi<TWFQueueEntry>(selectedId),
      twfQueueApi<TWFQueueEvent[]>(`${selectedId}/history`),
    ])
      .then(([entry, events]) => {
        if (cancelled) return;
        setDetail(entry);
        setHistory(events);
        setError("");
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, refreshKey]);
  async function loadOlder() {
    if (!nextCursor || loadingOlder) return;
    setLoadingOlder(true);
    const epoch = requestEpoch.current;
    try {
      const query = new URLSearchParams({ limit: "50", cursor: nextCursor });
      if (stateFilter !== "ALL") query.set("state", stateFilter);
      const page = await twfQueueApi<TWFQueuePage>(`?${query}`);
      if (epoch !== requestEpoch.current) return;
      setEntries((previous) => {
        const seen = new Set(previous.map((entry) => entry.queue_entry_id));
        return [
          ...previous,
          ...page.items.filter((entry) => !seen.has(entry.queue_entry_id)),
        ];
      });
      setNextCursor(page.next_cursor);
      setError("");
    } catch (e) {
      if (epoch !== requestEpoch.current) return;
      if (e instanceof TWFQueueApiError && e.code === "INVALID_CURSOR") {
        await refresh("Queue page expired. Returned to newest entries.");
      } else {
        setError((e as Error).message);
      }
    } finally {
      setLoadingOlder(false);
    }
  }
  async function changeState(entry: TWFQueueEntry) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const path = entry.queue_state === "READY" ? "hold" : "release";
      const updated = await twfQueueApi<TWFQueueEntry>(
        `${entry.queue_entry_id}/${path}`,
        { expected_version: entry.version },
      );
      setDetail(updated);
      await refresh();
      setHistory(
        await twfQueueApi<TWFQueueEvent[]>(`${entry.queue_entry_id}/history`),
      );
    } catch (e) {
      setError((e as Error).message);
      await refresh();
      if (selectedId) {
        try {
          setDetail(await twfQueueApi<TWFQueueEntry>(selectedId));
        } catch {
          // Preserve the actionable request error above.
        }
      }
    } finally {
      setBusy(false);
    }
  }
  const active = detail?.queue_entry_id === selectedId ? detail : null;
  const ready = entries.filter((entry) => entry.queue_state === "READY").length;
  const held = entries.filter((entry) => entry.queue_state === "HELD").length;
  return (
    <>
      <p className="orders-boundary" role="note">
        Broker submission is not enabled in OE-3. TWF Queue entries wait for
        governed execution in a later phase.
      </p>
      {error && (
        <p className="broker-notice" role="alert">
          {error} <button onClick={() => void refresh()}>Retry</button>
        </p>
      )}
      <div className="twf-queue-summary" aria-label="Loaded Queue page summary">
        {(
          [
            ["Loaded", entries.length, "stack"],
            ["Ready loaded", ready, "check"],
            ["Held loaded", held, "history"],
          ] as const
        ).map(([label, count, icon]) => (
          <div className="twf-queue-summary-card" key={label}>
            <span className="twf-queue-summary-icon">
              <Icon name={icon} />
            </span>
            <span>
              <small>{label}</small>
              <strong>{count}</strong>
            </span>
          </div>
        ))}
      </div>
      <div
        className={`orders-layout${selectedId ? " orders-layout-detail" : ""}`}
      >
        <section className="orders-list" aria-label="TWF Queue">
          <div className="orders-list-head">
            <h2>TWF Queue</h2>
            <span>Newest admissions first · execution remains FIFO</span>
          </div>
          <div className="orders-queue-filters" aria-label="Queue state filter">
            {(["ALL", "READY", "HELD"] as const).map((value) => (
              <button
                key={value}
                aria-pressed={stateFilter === value}
                onClick={() => {
                  if (stateFilter === value) return;
                  setLoading(true);
                  setStateFilter(value);
                }}
              >
                {value === "ALL" ? "All" : value === "READY" ? "Ready" : "Held"}
              </button>
            ))}
          </div>
          {loading ? (
            <p role="status">Loading Queue…</p>
          ) : entries.length === 0 ? (
            <div className="orders-empty">
              <strong>No Queue entries yet</strong>
              <p>Choose Add to Queue on a READY TWF Order.</p>
            </div>
          ) : (
            <div className="orders-table-scroll">
              <table className="orders-table">
                <thead>
                  <tr>
                    <th>Queue ID</th>
                    <th>Order ID</th>
                    <th>Admitted</th>
                    <th>Instrument</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Order Type</th>
                    <th>Queue State</th>
                    <th>Age</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr
                      key={entry.queue_entry_id}
                      className={
                        selectedId === entry.queue_entry_id ? "selected" : ""
                      }
                    >
                      <td>
                        <button
                          className="orders-id"
                          aria-label={`View Queue entry ${entry.queue_entry_id}`}
                          onClick={() => {
                            onSelect(entry.queue_entry_id);
                            setTab("Overview");
                          }}
                        >
                          {entry.queue_entry_id.slice(0, 8)}…
                        </button>
                      </td>
                      <td>
                        <button
                          className="orders-id"
                          onClick={() => onViewOrder(entry.twf_order_id)}
                        >
                          {entry.twf_order_id.slice(0, 8)}…
                        </button>
                      </td>
                      <td>{displayDate(entry.admitted_at)}</td>
                      <td>
                        <strong>{entry.order.instrument.symbol}</strong>
                        <small>{entry.order.instrument.asset_class}</small>
                      </td>
                      <td>{entry.order.terms.side}</td>
                      <td>{entry.order.terms.quantity}</td>
                      <td>{entry.order.terms.order_type}</td>
                      <td>
                        <span
                          className={`twf-order-state twf-queue-state-${entry.queue_state.toLowerCase()}`}
                        >
                          {entry.queue_state}
                        </span>
                      </td>
                      <td>{displayAge(entry.admitted_at)}</td>
                      <td>
                        <button
                          disabled={busy}
                          onClick={() => void changeState(entry)}
                        >
                          {entry.queue_state === "READY" ? "Hold" : "Release"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="orders-queue-pagination">
            <span>Showing {entries.length} newest-first · owner-scoped</span>
            {nextCursor && (
              <button disabled={loadingOlder} onClick={() => void loadOlder()}>
                {loadingOlder ? "Loading…" : "Load older"}
              </button>
            )}
            <button onClick={() => void refresh()}>Back to newest</button>
          </div>
        </section>
        {selectedId && (
          <aside className="orders-detail" aria-label="Queue details">
            <div className="orders-detail-head">
              <h2>Queue Details</h2>
              <button
                aria-label="Close Queue details"
                onClick={() => onSelect(null)}
              >
                ×
              </button>
            </div>
            {!active ? (
              <p role="status">Loading Queue entry…</p>
            ) : (
              <>
                <div className="orders-detail-summary">
                  <strong>{active.order.instrument.symbol}</strong>
                  <span
                    className={`twf-order-state twf-queue-state-${active.queue_state.toLowerCase()}`}
                  >
                    {active.queue_state}
                  </span>
                  <small>{active.queue_entry_id}</small>
                  <button
                    disabled={busy}
                    onClick={() => void changeState(active)}
                  >
                    {active.queue_state === "READY" ? "Hold" : "Release"}
                  </button>
                </div>
                <nav
                  className="orders-detail-tabs"
                  aria-label="Queue detail sections"
                >
                  {(["Overview", "TWF Order", "Queue History"] as const).map(
                    (value) => (
                      <button
                        key={value}
                        aria-current={tab === value ? "page" : undefined}
                        onClick={() => setTab(value)}
                      >
                        {value}
                      </button>
                    ),
                  )}
                </nav>
                {tab === "Overview" && (
                  <dl className="orders-facts">
                    <div>
                      <dt>Queue ID</dt>
                      <dd>{active.queue_entry_id}</dd>
                    </div>
                    <div>
                      <dt>Queue state</dt>
                      <dd>{active.queue_state}</dd>
                    </div>
                    <div>
                      <dt>Admitted</dt>
                      <dd>{displayDate(active.admitted_at)}</dd>
                    </div>
                    <div>
                      <dt>Age</dt>
                      <dd>{displayAge(active.admitted_at)}</dd>
                    </div>
                    <div>
                      <dt>Order ID</dt>
                      <dd>{active.twf_order_id}</dd>
                    </div>
                    <div>
                      <dt>Order state</dt>
                      <dd>{active.order.state}</dd>
                    </div>
                    <div>
                      <dt>Actor</dt>
                      <dd>{active.created_by}</dd>
                    </div>
                    {active.reason_message && (
                      <div>
                        <dt>Reason</dt>
                        <dd>{active.reason_message}</dd>
                      </div>
                    )}
                  </dl>
                )}
                {tab === "TWF Order" && (
                  <div className="orders-validation">
                    <p>
                      {active.order.instrument.symbol} ·{" "}
                      {active.order.terms.side} {active.order.terms.quantity} ·{" "}
                      {active.order.terms.order_type}
                    </p>
                    <button
                      className="orders-id"
                      onClick={() => onViewOrder(active.twf_order_id)}
                    >
                      View exact TWF Order
                    </button>
                  </div>
                )}
                {tab === "Queue History" && (
                  <ol className="orders-history">
                    {history.map((event) => (
                      <li key={event.event_id}>
                        <strong>
                          #{event.sequence} {event.event_type}
                        </strong>
                        <small>
                          {displayDate(event.occurred_at)} · {event.actor}
                        </small>
                        <span>
                          {event.from_state || "—"} → {event.to_state}
                          {event.reason_message
                            ? ` · ${event.reason_message}`
                            : ""}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </>
            )}
          </aside>
        )}
      </div>
    </>
  );
}
