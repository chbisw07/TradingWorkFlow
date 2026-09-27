"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { InstrumentSearch } from "./instrument-search";
import { useBrokerSession } from "./broker-session";
import {
  effectiveBrokerRoomState,
  datasetStale,
  type RoomObservation,
} from "../../lib/broker-room-status";
import {
  roomViews,
  type RoomView,
  type Portfolio,
  type NativeDataset,
  type NativeRow,
} from "../../lib/portfolio";

const title = (s: string) =>
  s === "dashboard" ? "Overview" : s.charAt(0).toUpperCase() + s.slice(1);
const amount = (v: string | number | null | undefined) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(
        Number(v),
      );
const pnl = (v: string | null | undefined) =>
  v == null ? "—" : `${Number(v) > 0 ? "+" : ""}${amount(v)}`;
const reasons: Record<string, string> = {
  AUTH_REQUIRED: "Not connected. Configure and connect your account.",
  AUTH_EXPIRED: "Re-authentication required. Reconnect to refresh your data.",
  TIMEOUT: "The broker took too long to respond. Try refreshing.",
  RATE_LIMITED: "The broker's read limit was reached. Wait before refreshing.",
  UNAVAILABLE: "The broker is temporarily unavailable.",
  INVALID_RESPONSE: "The broker returned an unreadable response.",
  TOO_LARGE: "The broker response exceeded the safe read limit.",
  PARTIAL_RESPONSE:
    "Some broker rows could not be read. Totals are unavailable.",
};
function DatasetState({ data, now }: { data: NativeDataset; now: number }) {
  const meta = data.metadata;
  const stale = datasetStale(data, now);
  return (
    <>
      <p role="status" className="broker-health">
        {data.rows === null
          ? "Unavailable"
          : stale
            ? "Stale · refresh to update"
            : "Recently received"}{" "}
        · {meta.completeness.toLowerCase()}
        {" · "}
        {meta.received_at ? "Received" : "Attempted"}{" "}
        {new Date(meta.received_at || meta.attempted_at).toLocaleTimeString()}
      </p>
      {meta.failure_code && (
        <p role="status">
          {reasons[meta.failure_code] ||
            "Connection changed. Refresh to continue."}
        </p>
      )}
      <details className="broker-diagnostics">
        <summary>Data details</summary>
        <p>
          Source: {meta.source} · Source time:{" "}
          {meta.source_as_of || "Not supplied"}. Prices are observations, not
          streaming quotes.
        </p>
        <p>
          Read health: {meta.health} · Retrieval freshness window:{" "}
          {meta.freshness_policy_seconds}s · Connection generation:{" "}
          {meta.connection_generation} · Rejected rows: {meta.rejected_rows}
        </p>
      </details>
    </>
  );
}
function Instrument({ row }: { row: NativeRow }) {
  const i = row.instrument;
  return (
    <>
      <strong>{i.symbol}</strong>
      <small>
        {i.exchange}
        {i.segment ? ` · ${i.segment}` : ""}
      </small>
      {i.derivative_kind && (
        <small>
          {i.name || "Underlying unknown"} · {i.expiry} · {amount(i.strike)}{" "}
          {i.derivative_kind}
        </small>
      )}
      <details className="broker-instrument-details">
        <summary>Instrument details</summary>
        <p>
          Native ID: {i.native_id} · Mapping: {i.canonical_id || "Unmapped"} ·
          Catalog: {i.catalog_state.toLowerCase()}
        </p>
        <p>
          Version: {i.catalog_version || "Unavailable"} · Lot:{" "}
          {amount(i.lot_size)} · Tick: {amount(i.tick_size)}
        </p>
        <p>
          Overnight: {amount(row.overnight_quantity)} · Buy:{" "}
          {amount(row.buy_quantity)} @ {amount(row.buy_average)} · Sell:{" "}
          {amount(row.sell_quantity)} @ {amount(row.sell_average)} · Multiplier:{" "}
          {amount(row.multiplier)}
        </p>
        <p>
          Used: {amount(row.used_quantity)} · Available:{" "}
          {amount(row.available_quantity)} · Unsettled:{" "}
          {amount(row.unsettled_quantity)} · Settled:{" "}
          {amount(row.settled_quantity)} · Authorised:{" "}
          {amount(row.authorised_quantity)}
        </p>
        <p>
          Collateral: {amount(row.collateral_quantity)} {row.collateral_type} ·
          Financed quantity: {amount(row.financed_quantity)} · Financing value:{" "}
          {amount(row.financed_value)}
        </p>
        <p>
          Previous close: {amount(row.close_price)} · Day change:{" "}
          {pnl(row.day_change)} ({pnl(row.day_change_percent)}%)
        </p>
      </details>
    </>
  );
}
function Rows({
  rows,
  positions = false,
  incomplete = false,
  name,
}: {
  rows: NativeRow[] | null;
  positions?: boolean;
  incomplete?: boolean;
  name: string;
}) {
  if (rows === null)
    return <p className="broker-notice">{name} unavailable.</p>;
  if (!rows.length)
    return (
      <p className="broker-notice">
        No {incomplete ? "readable " : ""}
        {name.toLowerCase()}
        {incomplete ? " rows" : ""}
      </p>
    );
  return (
    <div
      className="broker-table-scroll"
      role="region"
      aria-label={`${name} table`}
      tabIndex={0}
    >
      <table>
        <caption>{name} · INR · — means unavailable</caption>
        <thead>
          <tr>
            {(positions
              ? [
                  "Instrument",
                  "Product",
                  "Qty",
                  "Avg",
                  "LTP",
                  "Realized",
                  "Unrealized",
                  "Total P&L",
                ]
              : ["Instrument", "Qty", "Avg", "LTP", "Value", "P&L", "P&L %"]
            ).map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={`${row.instrument.native_id}-${row.instrument.exchange}-${row.product}`}
            >
              <td>
                <Instrument row={row} />
              </td>
              {positions && (
                <td>
                  {row.product}
                  {!row.product_known && <small>Unrecognized product</small>}
                </td>
              )}
              <td>{amount(row.quantity)}</td>
              <td>{amount(row.average_price)}</td>
              <td>{amount(row.last_price)}</td>
              {positions ? (
                <>
                  <td>{pnl(row.realized_pnl)}</td>
                  <td>{pnl(row.unrealized_pnl)}</td>
                  <td>{pnl(row.pnl)}</td>
                </>
              ) : (
                <>
                  <td>{amount(row.current_value)}</td>
                  <td>{pnl(row.pnl)}</td>
                  <td>{pnl(row.pnl_percent)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function RealBrokerRoom({
  accountId,
  view = "dashboard",
}: {
  accountId: string;
  view?: RoomView;
}) {
  return (
    <BrokerRoomSession
      key={`${accountId}:${view === "instruments" ? "reference" : "portfolio"}`}
      accountId={accountId}
      view={view}
    />
  );
}

function BrokerRoomSession({
  accountId,
  view,
}: {
  accountId: string;
  view: RoomView;
}) {
  const session = useBrokerSession();
  const [observation, setObservation] = useState<RoomObservation | null>(null);
  const data = observation?.value || null;
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [now, setNow] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const reading = view !== "instruments";
  useEffect(() => {
    const c = new AbortController();
    if (!reading) return () => c.abort();
    const startedAt = performance.now();
    fetch(`/api/v1/broker-portfolio/accounts/${accountId}`, {
      cache: "no-store",
      signal: c.signal,
    })
      .then(async (r) => {
        if (!r.ok)
          throw new Error(
            r.status === 401
              ? "Your session expired. Sign in again."
              : r.status === 404
                ? "This broker account is unavailable."
                : r.status === 409
                  ? "Connection changed during the read. Refresh to continue."
                  : "Broker observations are unavailable. Try again.",
          );
        return r.json() as Promise<Portfolio>;
      })
      .then((value) => {
        if (!c.signal.aborted) {
          if (
            value.broker_account_id !== accountId ||
            value.provider_id !== "zerodha"
          ) {
            setObservation(null);
            setError("This broker account is unavailable.");
            return;
          }
          setObservation({ value, startedAt });
          setError("");
          setNow(Date.now());
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setObservation(null);
          setError(e.message);
        }
      });
    return () => c.abort();
  }, [accountId, attempt, reading]);
  const {
    connection,
    headline,
    retained,
    actionLabel,
    label: accountLabel,
  } = effectiveBrokerRoomState({
    accountId,
    connections: session.connections,
    sessionObservedAt: session.observedAt,
    sessionError: session.error,
    observation,
    view,
    now,
    readError: error,
  });
  return (
    <div className="broker-room broker-content">
      <header className="broker-room-heading">
        <div>
          <h1>Zerodha{accountLabel ? ` · ${accountLabel}` : ""}</h1>
          <p
            className="broker-capability"
            role="status"
            aria-label="Broker read status"
          >
            <span>{headline}</span>
            <span>TRADING DISABLED</span>
          </p>
        </div>
      </header>
      {connection && (
        <p role="status">
          {connection === "CONNECTED"
            ? "Connected"
            : connection === "REAUTH_REQUIRED"
              ? "Re-authentication required"
              : connection === "AUTH_IN_PROGRESS" ||
                  connection === "AUTHENTICATING"
                ? "Connecting"
                : connection === "ERROR" || connection === "UNAVAILABLE"
                  ? "Connection unavailable"
                  : "Not connected"}
          {actionLabel && (
            <>
              {" · "}
              <Link href={`/brokers/manage/accounts/${accountId}`}>
                {actionLabel}
              </Link>
            </>
          )}
        </p>
      )}
      {retained && (
        <p role="status">
          Showing last available snapshot. These observations do not describe
          the current connection.
        </p>
      )}
      <nav className="broker-tabs" aria-label="Zerodha functions">
        {roomViews.map((tab) => (
          <Link
            key={tab}
            href={`/brokers/zerodha/${accountId}/${tab}`}
            aria-current={view === tab ? "page" : undefined}
          >
            {title(tab)}
          </Link>
        ))}
      </nav>
      {view === "instruments" ? (
        <InstrumentSearch accountId={accountId} embedded />
      ) : (
        <section className="broker-surface">
          <div className="broker-room-heading">
            <h2>{title(view)}</h2>
            <button
              className="quiet-button"
              onClick={() => {
                setObservation(null);
                setError("");
                setAttempt((x) => x + 1);
              }}
            >
              Refresh data
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
          {!data && !error && <p role="status">Loading broker observations…</p>}
          {data && (
            <>
              {view === "dashboard" ? (
                <>
                  <dl className="broker-metrics">
                    {Object.entries({
                      Holdings: data.summary.holdings_count,
                      "Holdings value · INR": data.summary.holdings_value,
                      "Open positions": data.summary.open_positions_count,
                      "Realized P&L · INR": data.summary.realized_pnl,
                      "Unrealized P&L · INR": data.summary.unrealized_pnl,
                      "Position P&L · INR": data.summary.position_pnl,
                    }).map(([label, value]) => (
                      <div key={label}>
                        <dt>{label}</dt>
                        <dd>{amount(value)}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="broker-dataset-grid">
                    {(["holdings", "positions"] as const).map((key) => (
                      <section key={key}>
                        <h3>
                          <Link href={`/brokers/zerodha/${accountId}/${key}`}>
                            {title(key)}
                          </Link>
                        </h3>
                        <DatasetState data={data[key]} now={now} />
                      </section>
                    ))}
                  </div>
                </>
              ) : (
                <>
                  <DatasetState data={data[view]} now={now} />
                  <details className="broker-diagnostics">
                    <summary>About these values</summary>
                    <p>
                      {view === "holdings"
                        ? "Value uses the reported quantity. Unsettled and pledged quantities are separate details, not trading availability."
                        : "Net positions are shown below. Realized and unrealized fields are the broker's intraday returns; day activity is separate."}
                    </p>
                  </details>
                  <Rows
                    rows={data[view].rows}
                    incomplete={data[view].metadata.completeness !== "COMPLETE"}
                    positions={view === "positions"}
                    name={title(view)}
                  />
                  {view === "positions" &&
                    data.positions.activity_rows !== null && (
                      <details>
                        <summary>
                          Day activity · not additional net positions
                        </summary>
                        <Rows
                          rows={data.positions.activity_rows}
                          incomplete={
                            data.positions.metadata.completeness !== "COMPLETE"
                          }
                          positions
                          name="Day activity"
                        />
                      </details>
                    )}
                </>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
