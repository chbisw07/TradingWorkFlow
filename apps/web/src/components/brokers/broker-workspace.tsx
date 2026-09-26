"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  brokerViews,
  type BrokerView,
  type Observation,
  type Overview,
  type Snapshot,
} from "../../lib/brokers";

const title = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);
const amount = (value: string | number | null | undefined) =>
  value == null
    ? "Unknown"
    : new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(
        Number(value),
      );
const stamp = (value: string | null) =>
  value
    ? value.replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC")
    : "Unknown source time";
const sum = (values: (string | null)[] | null) =>
  values === null || values.some((value) => value === null)
    ? null
    : values.reduce<number>((total, value) => total + Number(value), 0);

function Provenance({ value }: { value: Observation }) {
  return (
    <div className="broker-provenance">
      <p>
        <strong>{value.health}</strong> · {value.freshness} ·{" "}
        {value.completeness}
      </p>
      <p>
        Source: {value.source} · As of{" "}
        <time dateTime={value.source_as_of ?? undefined}>
          {stamp(value.source_as_of)}
        </time>
      </p>
      <p>
        Fetched{" "}
        <time dateTime={value.fetched_at}>{stamp(value.fetched_at)}</time> ·{" "}
        {value.revision} · Freshness policy: {value.freshness_policy_seconds}s
      </p>
    </div>
  );
}

function Table({
  name,
  columns,
  rows,
}: {
  name: string;
  columns: string[];
  rows: ReactNode[][] | null;
}) {
  if (rows === null)
    return (
      <p role="status" className="broker-notice">
        {name} unavailable. No observation received.
      </p>
    );
  if (!rows.length)
    return (
      <p role="status" className="broker-notice">
        No {name.toLowerCase()} in this snapshot.
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
        <caption>{name}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td key={j}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metrics({ snapshot }: { snapshot: Snapshot }) {
  const { holdings, positions, orders, funds } = snapshot;
  const values = [
    ["Available cash · INR", amount(funds.values?.available_cash)],
    [
      "Holdings value · INR",
      amount(sum(holdings.rows?.map((row) => row.current_value) ?? null)),
    ],
    ["Holdings", amount(holdings.rows?.length)],
    ["Positions", amount(positions.rows?.length)],
    ["Observed orders", amount(orders.rows?.length)],
    [
      "Unrealized position P&L · INR",
      amount(sum(positions.rows?.map((row) => row.unrealized_pnl) ?? null)),
    ],
    [
      "Realized position P&L · INR",
      amount(sum(positions.rows?.map((row) => row.realized_pnl) ?? null)),
    ],
  ];
  return (
    <dl className="broker-metrics">
      {values.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Room({ snapshot, view }: { snapshot: Snapshot; view: BrokerView }) {
  const { account, operation } = snapshot;
  return (
    <>
      <div className="broker-room-heading">
        <div>
          <p className="eyebrow">{account.provider_id} / Personal room</p>
          <h1>{account.label}</h1>
        </div>
        <span className="broker-mode">{account.mode}</span>
      </div>
      <p className="broker-health" role="status">
        Connection: {operation.connection} · Read health: {operation.read}
        {operation.error ? ` · ${operation.error}` : ""}
      </p>
      <p className="broker-account-id">Account: {account.broker_account_id}</p>
      <nav className="broker-tabs" aria-label="Broker room views">
        {brokerViews.map((tab) => (
          <Link
            key={tab}
            href={`/brokers/${account.broker_account_id}/${tab}`}
            aria-current={view === tab ? "page" : undefined}
          >
            {title(tab)}
          </Link>
        ))}
      </nav>
      <section className="broker-surface" aria-labelledby="broker-view-title">
        <h2 id="broker-view-title">{title(view)}</h2>
        {view === "dashboard" && (
          <>
            <p className="panel-intro">
              Summary of the same observed rows shown in each account view.
              Values remain qualified by the dataset states below.
            </p>
            <Metrics snapshot={snapshot} />
            <div className="broker-dataset-grid">
              {(["holdings", "positions", "orders", "funds"] as const).map(
                (dataset) => (
                  <section key={dataset}>
                    <h3>{title(dataset)}</h3>
                    <Provenance value={snapshot[dataset].metadata} />
                  </section>
                ),
              )}
            </div>
          </>
        )}
        {view === "holdings" && (
          <>
            <Provenance value={snapshot.holdings.metadata} />
            <Table
              name="Holdings"
              columns={[
                "Instrument / broker symbol",
                "Exchange",
                "Quantity",
                "Average cost",
                "LTP",
                "Value · INR",
                "P&L · INR",
                "P&L %",
              ]}
              rows={
                snapshot.holdings.rows?.map((row) => [
                  <span key="id">
                    {row.instrument.canonical_id ?? "Unmapped"}
                    <small>
                      {row.instrument.broker_symbol} · Native{" "}
                      {row.instrument.native_id}
                    </small>
                  </span>,
                  row.instrument.exchange,
                  amount(row.quantity),
                  amount(row.average_cost),
                  amount(row.last_price),
                  amount(row.current_value),
                  amount(row.pnl),
                  amount(row.pnl_percent),
                ]) ?? null
              }
            />
          </>
        )}
        {view === "positions" && (
          <>
            <Provenance value={snapshot.positions.metadata} />
            <Table
              name="Positions"
              columns={[
                "Instrument / broker symbol",
                "Product",
                "Quantity · shares",
                "Average price",
                "LTP",
                "Realized P&L · INR",
                "Unrealized P&L · INR",
                "Broker state",
              ]}
              rows={
                snapshot.positions.rows?.map((row) => [
                  <span key="id">
                    {row.instrument.canonical_id ??
                      "Unmapped — excluded from canonical netting"}
                    <small>
                      {row.instrument.broker_symbol} · Native{" "}
                      {row.instrument.native_id}
                    </small>
                  </span>,
                  row.product,
                  amount(row.quantity),
                  amount(row.average_price),
                  amount(row.last_price),
                  amount(row.realized_pnl),
                  amount(row.unrealized_pnl),
                  row.broker_state,
                ]) ?? null
              }
            />
          </>
        )}
        {view === "orders" && (
          <>
            <p className="panel-intro">
              Observed broker orders only. No order creation or execution
              actions.
            </p>
            <Provenance value={snapshot.orders.metadata} />
            <Table
              name="Orders"
              columns={[
                "Broker order ID",
                "Instrument",
                "Side",
                "Quantity",
                "Filled",
                "Remaining",
                "Price · INR",
                "Observed status",
                "Timestamp / reason",
              ]}
              rows={
                snapshot.orders.rows?.map((row) => [
                  row.broker_order_id,
                  row.instrument.canonical_id ?? row.instrument.broker_symbol,
                  row.side,
                  amount(row.quantity),
                  amount(row.filled_quantity),
                  amount(row.remaining_quantity),
                  amount(row.price),
                  row.status,
                  <span key="time">
                    {stamp(row.observed_at)}
                    {row.reason && <small>{row.reason}</small>}
                  </span>,
                ]) ?? null
              }
            />
          </>
        )}
        {view === "funds" && (
          <>
            <Provenance value={snapshot.funds.metadata} />
            {snapshot.funds.values ? (
              <dl className="broker-metrics">
                {(["available_cash", "used_margin", "collateral"] as const).map(
                  (key) => (
                    <div key={key}>
                      <dt>{title(key.replaceAll("_", " "))} · INR</dt>
                      <dd>{amount(snapshot.funds.values?.[key])}</dd>
                    </div>
                  ),
                )}
              </dl>
            ) : (
              <p role="status" className="broker-notice">
                Funds unavailable. Values are unknown.
              </p>
            )}
            <p className="panel-intro">
              Funds belong to this account. They cannot fund another broker
              account.
            </p>
          </>
        )}
      </section>
      <p className="broker-deferred">
        Unavailable in this foundation: Watchlist · Instrument Search · New
        Order
      </p>
    </>
  );
}

function OverviewView({ data }: { data: Overview }) {
  const labels = new Map(
    data.accounts.map((item) => [
      item.account.broker_account_id,
      item.account.label,
    ]),
  );
  return (
    <>
      <div className="broker-room-heading">
        <div>
          <p className="eyebrow">BROKER WORKSPACE / READ ONLY</p>
          <h1>Broker overview</h1>
        </div>
        <span className="broker-mode">
          {[...new Set(data.accounts.map(({ account }) => account.mode))].join(
            " / ",
          )}
        </span>
      </div>
      <p className="broker-lead">Three separate rooms. One analytical view.</p>
      <div className="broker-cards">
        {data.accounts.map((item) => (
          <section key={item.account.broker_account_id} className="broker-card">
            <p className="eyebrow">
              {
                data.providers.find(
                  (p) => p.provider_id === item.account.provider_id,
                )?.name
              }{" "}
              · {item.account.mode}
            </p>
            <h2>
              <Link
                href={`/brokers/${item.account.broker_account_id}/dashboard`}
              >
                {item.account.label}
              </Link>
            </h2>
            <p>
              {item.operation.connection} · {item.operation.read}
            </p>
            {item.operation.error && (
              <p role="status">{item.operation.error}</p>
            )}
            <dl>
              <dt>Available cash · INR</dt>
              <dd>{amount(item.funds.values?.available_cash)}</dd>
              <dt>Positions / observed orders</dt>
              <dd>
                {amount(item.positions.rows?.length)} /{" "}
                {amount(item.orders.rows?.length)}
              </dd>
            </dl>
            <p className="broker-qualification">
              Positions: {item.positions.metadata.freshness} ·{" "}
              {item.positions.metadata.completeness}
            </p>
            <Link
              className="broker-open"
              href={`/brokers/${item.account.broker_account_id}/dashboard`}
            >
              Open {item.account.label} →
            </Link>
          </section>
        ))}
      </div>
      <section className="broker-surface" aria-labelledby="aggregate-title">
        <h2 id="aggregate-title">Analytical position aggregate</h2>
        <p className="panel-intro">
          Compatible position quantities only. Holdings are separate. Netting
          does not merge accounts, funds or execution authority.
        </p>
        <p className="broker-qualification" role="status">
          {data.unmapped_position_count} unmapped position rows remain in their
          rooms and are excluded from canonical netting.{" "}
          {data.missing_position_accounts} accounts have missing position data.
        </p>
        {data.position_aggregates.length === 0 && (
          <p>No canonical position observations.</p>
        )}
        {data.position_aggregates.map((group) => (
          <article
            className="broker-aggregate"
            key={[
              group.canonical_id,
              group.exchange,
              group.product,
              group.currency,
              group.quantity_unit,
            ].join(":")}
          >
            <div>
              <h3>{group.canonical_id}</h3>
              <p>
                {group.product} · {group.currency} · {group.quantity_unit}
              </p>
              <strong className="broker-net">{amount(group.quantity)}</strong>
              <p>
                {group.qualified
                  ? "Qualified subtotal — stale, partial or missing contributions"
                  : "Complete observed quantity"}
              </p>
            </div>
            <ul>
              {group.contributions.map((contribution) => (
                <li key={contribution.broker_account_id}>
                  <Link
                    href={`/brokers/${contribution.broker_account_id}/positions`}
                  >
                    {labels.get(contribution.broker_account_id)}
                  </Link>
                  <strong>{amount(contribution.quantity)}</strong>
                  <small>
                    {contribution.metadata.freshness} ·{" "}
                    {contribution.metadata.completeness} ·{" "}
                    {stamp(contribution.metadata.source_as_of)} ·{" "}
                    {contribution.metadata.revision}
                  </small>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </section>
    </>
  );
}

export function BrokerWorkspace({
  accountId,
  view = "dashboard",
}: {
  accountId?: string;
  view?: BrokerView;
}) {
  const [result, setResult] = useState<{
    overview: Overview;
    room: Snapshot | null;
  } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    async function get(path: string) {
      const response = await fetch(`/api/v1/brokers/${path}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok)
        throw new Error(
          response.status === 401
            ? "Your session expired. Sign in again."
            : response.status === 404
              ? "Broker account unavailable for this user."
              : "Broker observations unavailable. Try again.",
        );
      return response.json();
    }
    Promise.all([
      get("overview"),
      accountId ? get(`accounts/${accountId}`) : Promise.resolve(null),
    ])
      .then(([overview, room]: [Overview, Snapshot | null]) => {
        if (!controller.signal.aborted) setResult({ overview, room });
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure.message);
      });
    return () => controller.abort();
  }, [accountId, attempt]);
  if (error)
    return (
      <section className="broker-surface">
        <h1>Broker Workspace</h1>
        <p role="alert">{error}</p>
        <button
          className="quiet-button"
          onClick={() => {
            setError("");
            setResult(null);
            setAttempt((value) => value + 1);
          }}
        >
          Try again
        </button>
        <Link href="/login">Sign in</Link>
      </section>
    );
  if (!result)
    return (
      <section aria-busy="true">
        <h1>Broker Workspace</h1>
        <p role="status">Loading broker observations…</p>
      </section>
    );
  return (
    <div className="broker-workspace">
      <nav className="broker-account-nav" aria-label="Broker accounts">
        <p className="eyebrow">PERSONAL ROOMS</p>
        <Link href="/brokers" aria-current={!accountId ? "page" : undefined}>
          Overview
        </Link>
        {result.overview.accounts.map(({ account }) => (
          <Link
            key={account.broker_account_id}
            href={`/brokers/${account.broker_account_id}/dashboard`}
            aria-current={
              accountId === account.broker_account_id ? "page" : undefined
            }
          >
            {account.label}
            <small>{account.mode}</small>
          </Link>
        ))}
      </nav>
      <div className="broker-content">
        <p className="broker-fixture-clock">
          {result.overview.accounts.every(
            ({ account }) => account.mode === "SYNTHETIC",
          )
            ? "Deterministic synthetic snapshots · Scenario clock "
            : "Snapshot reference time "}
          {stamp(result.overview.scenario_time)}
          {result.overview.accounts.every(
            ({ account }) => account.mode === "SYNTHETIC",
          )
            ? " · No live market data"
            : ""}
        </p>
        {result.room ? (
          <Room snapshot={result.room} view={view} />
        ) : (
          <OverviewView data={result.overview} />
        )}
      </div>
    </div>
  );
}
