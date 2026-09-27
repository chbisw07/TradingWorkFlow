"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

type Catalog = {
  account_label: string;
  provider_id: string;
  version: string | null;
  freshness: string;
  completeness: string;
  row_count: number;
  fetched_at: string | null;
  verified_at: string | null;
  source_at: string | null;
  failure_code: string | null;
  refreshing: boolean;
  can_refresh: boolean;
  attempt_rejected_rows: number;
};
type Instrument = {
  id: string;
  native_id: string;
  exchange_id: string | null;
  symbol: string;
  name: string | null;
  exchange: string;
  segment: string;
  instrument_type: string;
  expiry: string | null;
  strike: string | null;
  derivative_kind: string | null;
  lot_size: number;
  tick_size: string;
  provider_id: string;
  catalog_version: string;
  fingerprint: string;
  canonical_id: string | null;
};
type Search = {
  catalog: Catalog;
  instruments: Instrument[];
  matched: number;
  limit: number;
  offset: number;
};
const stamp = (value: string | null) =>
  value
    ? value.replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC")
    : "Unknown";

const decimal = (value: string) =>
  value.includes(".")
    ? value.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "")
    : value;

export function InstrumentSearch({ accountId }: { accountId: string }) {
  return <InstrumentSearchSession key={accountId} accountId={accountId} />;
}

function InstrumentSearchSession({ accountId }: { accountId: string }) {
  // A search owns one immutable snapshot, including refreshes of its first page.
  const pinnedVersion = useRef<string | null>(null);
  const [query, setQuery] = useState("limit=25");
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Search | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const endpoint = `/api/v1/broker-catalog/accounts/${accountId}`;
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const values = new URLSearchParams(query);
    if (pinnedVersion.current) values.set("version", pinnedVersion.current);
    fetch(`${endpoint}/instruments?${values}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error(
            response.status === 401
              ? "Your session expired. Sign in again."
              : response.status === 404
                ? "This broker account is unavailable."
                : "Instrument search is unavailable. Try again.",
          );
        return response.json() as Promise<Search>;
      })
      .then((result) => {
        if (active) {
          pinnedVersion.current ??= result.catalog.version;
          setData(result);
        }
      })
      .catch((failure) => {
        if (active && failure.name !== "AbortError") setError(failure.message);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [endpoint, query, revision]);
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new URLSearchParams({ limit: "25" });
    for (const [key, value] of new FormData(event.currentTarget))
      if (typeof value === "string" && value.trim())
        values.set(key, value.trim());
    setError("");
    setData(null);
    pinnedVersion.current = null;
    setQuery(values.toString());
    setRevision((value) => value + 1);
  }
  function page(offset: number) {
    const values = new URLSearchParams(query);
    values.set("offset", String(offset));
    setData(null);
    setError("");
    setQuery(values.toString());
  }
  async function refresh() {
    setRefreshing(true);
    setError("");
    try {
      const response = await fetch(`${endpoint}/refresh`, {
        method: "POST",
        cache: "no-store",
      });
      if (!response.ok)
        throw new Error(
          response.status === 409
            ? "A refresh is already running or the connection changed. Try again shortly."
            : "Catalog refresh unavailable. Check your connection.",
        );
      setRevision((value) => value + 1);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setRefreshing(false);
    }
  }
  const catalog = data?.catalog;
  return (
    <section
      className="broker-surface catalog-room"
      aria-labelledby="catalog-title"
    >
      <nav className="broker-tabs" aria-label="Zerodha broker room">
        <Link href="/brokers#real-brokers">Brokers / connection</Link>
        <a href="#catalog-title" aria-current="page">
          Instrument Search
        </a>
      </nav>
      <div className="broker-room-heading">
        <div>
          <p className="eyebrow">
            ZERODHA / {catalog?.account_label || "PERSONAL ACCOUNT"}
          </p>
          <h1 id="catalog-title">Instrument Search</h1>
        </div>
        <span className="broker-mode">LIVE DATA · READ ONLY</span>
      </div>
      <p className="broker-safety-label">TRADING DISABLED</p>
      <p className="panel-intro">
        Search native listings and derivative contracts. Catalog values are
        reference data, not live quotes. Portfolio views, watchlists and order
        previews are deferred.
      </p>
      <form
        className="catalog-filters"
        onSubmit={search}
        aria-label="Instrument filters"
      >
        <label className="catalog-text">
          Search instruments
          <input
            name="text"
            maxLength={128}
            placeholder="HAL, a symbol or company name"
          />
        </label>
        <label>
          Underlying / name
          <input
            name="name"
            maxLength={128}
            placeholder="Provider-supplied name"
          />
        </label>
        <label>
          Segment
          <input
            name="segment"
            maxLength={32}
            list="catalog-segments"
            placeholder="NFO-OPT"
          />
          <datalist id="catalog-segments">
            <option value="NSE" />
            <option value="NFO-OPT" />
            <option value="NFO-FUT" />
            <option value="BSE" />
            <option value="MCX" />
          </datalist>
        </label>
        <label>
          Expiry
          <input name="expiry" type="date" />
        </label>
        <label>
          Strike
          <input
            name="strike"
            type="number"
            min="0"
            max="1000000000000"
            step="0.00000001"
          />
        </label>
        <label>
          Contract kind
          <select name="derivative_kind">
            <option value="">All contracts</option>
            <option value="CE">CE · Call</option>
            <option value="PE">PE · Put</option>
            <option value="FUT">FUT · Future</option>
          </select>
        </label>
        <label>
          Exchange
          <input name="exchange" maxLength={32} placeholder="NFO" />
        </label>
        <label>
          Instrument type
          <input
            name="instrument_type"
            maxLength={32}
            placeholder="EQ, CE, PE, FUT"
          />
        </label>
        <label>
          Trading symbol
          <input name="symbol" maxLength={128} />
        </label>
        <button className="quiet-button" type="submit">
          Search catalog
        </button>
      </form>
      <p className="panel-intro">
        Underlying names can be absent in the provider catalog. Use the trading
        symbol when a name is unavailable.
      </p>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading instrument catalog…</p>}
      {catalog && (
        <div className="broker-provenance" aria-label="Catalog provenance">
          <p role="status">
            Acquisition: <strong>{catalog.freshness}</strong> ·{" "}
            {catalog.completeness} · {catalog.row_count} native instruments
          </p>
          <p>
            Provider: {catalog.provider_id} · Source: Kite instrument master ·
            Catalog version: {catalog.version || "Not published"}
          </p>
          <p>
            Fetched: {stamp(catalog.fetched_at)} · Last verified:{" "}
            {stamp(catalog.verified_at)} · Source timestamp:{" "}
            {stamp(catalog.source_at)}
          </p>
          {catalog.failure_code && (
            <p role="status">
              {catalog.failure_code === "AUTH_REQUIRED"
                ? "Authentication required to refresh. Reconnect from Brokers."
                : `Refresh failed (${catalog.failure_code.replaceAll("_", " ")}). The last good catalog is retained.`}
            </p>
          )}
          {catalog.attempt_rejected_rows > 0 && (
            <p>
              {catalog.attempt_rejected_rows} rejected rows in the last attempt;
              incomplete data was not published.
            </p>
          )}
          <button
            className="quiet-button"
            disabled={refreshing || catalog.refreshing || !catalog.can_refresh}
            onClick={() => void refresh()}
          >
            {refreshing || catalog.refreshing
              ? "Refreshing catalog…"
              : "Refresh catalog"}
          </button>
        </div>
      )}
      {data && (
        <>
          <p role="status">{data.matched} matching instruments</p>
          {data.instruments.length === 0 && (
            <p>
              {catalog?.version
                ? "No instruments match these filters."
                : "No catalog is available yet. Connect Zerodha and refresh the catalog."}
            </p>
          )}
          <div className="catalog-results">
            {data.instruments.map((row) => (
              <article
                key={row.id}
                className="catalog-instrument"
                aria-label={`${row.exchange}:${row.symbol}`}
              >
                <p className="eyebrow">
                  {row.provider_id.toUpperCase()} / {row.exchange} /{" "}
                  {row.segment}
                </p>
                <h2>{row.symbol}</h2>
                <p>{row.name || "Name / underlying unavailable"}</p>
                <dl>
                  <div>
                    <dt>Type / contract</dt>
                    <dd>
                      {row.instrument_type} / {row.derivative_kind || "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Expiry</dt>
                    <dd>{row.expiry || "—"}</dd>
                  </div>
                  <div>
                    <dt>Strike</dt>
                    <dd>{row.strike === null ? "—" : decimal(row.strike)}</dd>
                  </div>
                  <div>
                    <dt>Lot size</dt>
                    <dd>{row.lot_size}</dd>
                  </div>
                  <div>
                    <dt>Tick size</dt>
                    <dd>{decimal(row.tick_size)}</dd>
                  </div>
                  <div>
                    <dt>Native identity</dt>
                    <dd>
                      {row.native_id} / {row.exchange_id || "—"}
                    </dd>
                  </div>
                </dl>
                <p className="panel-intro">
                  Canonical mapping:{" "}
                  {row.canonical_id || "Unmapped · native identity retained"}
                </p>
              </article>
            ))}
          </div>
          <nav
            className="broker-connection-actions"
            aria-label="Instrument result pages"
          >
            <button
              className="quiet-button"
              disabled={data.offset === 0}
              onClick={() => page(Math.max(0, data.offset - data.limit))}
            >
              Previous
            </button>
            <span>
              {data.instruments.length ? data.offset + 1 : 0}–
              {data.offset + data.instruments.length} of {data.matched}
            </span>
            <button
              className="quiet-button"
              disabled={
                data.offset + data.limit >= data.matched ||
                data.offset + data.limit > 10000
              }
              onClick={() => page(data.offset + data.limit)}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </section>
  );
}
