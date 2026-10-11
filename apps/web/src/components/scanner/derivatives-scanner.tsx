"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { OrderTicket } from "../brokers/order-ticket";
import { brokerApi, type Account } from "../../lib/brokers";
import type { Capability, Side } from "../../lib/broker-orders";
import type {
  OptionContract,
  OptionContractRequest,
  OptionMarketSnapshot,
} from "../../lib/options";
import { chainNumber as num, expiryLabel } from "../../lib/option-chain-client";
import { scannerApi } from "../../lib/scanner";
import {
  watchApi,
  type Watchlist,
  type WatchDetail,
} from "../../lib/watchlists";

type Field = {
  field: string;
  category: string;
  label: string;
  kind: "enum" | "multi" | "integer" | "number";
  values?: string[];
  operators: string[];
  minimum?: number;
  maximum?: number;
  unit?: string;
  provider_dependent?: boolean;
};
type Filter = {
  field: string;
  operator: string;
  value: string | number | number[] | string[];
};
type Config = {
  name: string;
  scanner_type: "DERIVATIVES";
  data_mode: "REAL";
  provider: "dhan";
  universe: {
    source: "CUSTOM" | "WATCHLIST";
    symbols: string[];
    watchlist_id?: string;
  };
  expiry_mode: "NEAREST" | "EXACT";
  exact_expiry: string | null;
  strike_window: 5 | 10 | 15 | 20;
  filters: Filter[];
  version: "1";
};
type Diagnostic = {
  filter: Filter;
  observed: string | number | null;
  threshold: unknown;
  passed: boolean | null;
  reason: string;
};
type Row = {
  contract: OptionContract;
  underlying: string;
  spot: string | null;
  expiry: string;
  dte: number;
  strike: string;
  option_type: "CE" | "PE";
  moneyness: string | null;
  strike_distance_percent: number | null;
  market: OptionMarketSnapshot;
  volume_percentile?: number | null;
  volume_chain_median?: number | null;
  volume_vs_chain_median?: number | null;
  volume_oi_percent?: number | null;
  relative_volume_cohort_size?: number;
  technical: Record<string, string | number | null>;
  instrument_metadata: {
    sector?: string | null;
    market_cap_category?: string | null;
  } | null;
  observed: Record<string, string | number | null>;
  provenance: {
    provider: string;
    market_source: string;
    source_time: string | null;
    received_at: string;
    freshness: string;
    cached: boolean;
  };
  outcome: "MATCH" | "NON_MATCH" | "NOT_EVALUATED";
  diagnostics: Diagnostic[];
  missing_evidence: string[];
  warnings: string[];
  reason: string;
};
type Run = {
  id: string;
  created_at: string;
  config: Config;
  counts: Record<string, number>;
  rows: Row[];
  underlyings: {
    symbol: string;
    outcome: string;
    failure: string | null;
    technical_failure?: string;
  }[];
};
type Saved = {
  id: string;
  config: Config;
  archived: boolean;
  updated_at: string;
};
const optionalResultColumns = [
  ["volume_vs_chain_median", "Vol/Median"],
  ["volume_oi_percent", "Vol/OI %"],
  ["bid", "Bid"],
  ["ask", "Ask"],
  ["strike_distance_percent", "Strike distance %"],
  ["delta", "Delta"],
  ["theta", "Theta"],
  ["rsi", "Underlying RSI"],
  ["sector", "Sector"],
] as const;
type OptionalResultColumn = (typeof optionalResultColumns)[number][0];
function optionalResultValue(row: Row, column: OptionalResultColumn): string {
  switch (column) {
    case "volume_vs_chain_median":
      return row.volume_vs_chain_median == null
        ? "—"
        : `${num(row.volume_vs_chain_median)}x`;
    case "volume_oi_percent":
      return row.volume_oi_percent == null
        ? "—"
        : `${num(row.volume_oi_percent)}%`;
    case "strike_distance_percent":
      return num(row.strike_distance_percent);
    case "rsi":
      return num(row.technical.rsi);
    case "sector":
      return row.instrument_metadata?.sector || "—";
    default:
      return num(row.market[column]);
  }
}
type Broker = { account: Account; capability: Capability };
const initial: Config = {
  name: "Options scan",
  scanner_type: "DERIVATIVES",
  data_mode: "REAL",
  provider: "dhan",
  universe: { source: "CUSTOM", symbols: [] },
  expiry_mode: "NEAREST",
  exact_expiry: null,
  strike_window: 10,
  filters: [],
  version: "1",
};
function parseSymbols(raw: string) {
  return [
    ...new Set(
      raw
        .split(/[\s,]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean),
    ),
  ];
}
function valueText(value: unknown): string {
  if (Array.isArray(value)) return value.join(" – ");
  return value == null ? "—" : String(value);
}
function filterText(filter: Filter, fields: Field[]) {
  const spec = fields.find((f) => f.field === filter.field);
  const unit =
    (spec?.unit === "x" || filter.field === "volume_oi_percent") && spec
      ? spec.unit
      : "";
  return `${spec?.label || filter.field} ${filter.operator === "between" ? "between" : filter.operator} ${valueText(filter.value)}${unit || ""}`;
}
function diagnosticObserved(diagnostic: Diagnostic): string {
  if (diagnostic.observed == null) return "Unavailable";
  const suffix =
    diagnostic.filter.field === "volume_vs_chain_median"
      ? "x"
      : diagnostic.filter.field === "volume_oi_percent"
        ? "%"
        : "";
  return `${valueText(diagnostic.observed)}${suffix}`;
}
const resultColumnHelp: Record<string, string> = {
  "Vol Pctl": "Volume percentile within the same underlying and expiry chain",
  "Vol/Median": "Contract volume divided by the chain median volume",
  "Vol/OI %": "Contract volume as a percentage of current open interest",
};
function expiredContract(contract: OptionContract): boolean {
  const today = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  return (
    contract.is_active === false ||
    contract.expiry < today ||
    (contract.last_trading_date != null && contract.last_trading_date < today)
  );
}

function tradeContract(contract: OptionContract): OptionContractRequest {
  const { exchange, underlying_symbol, expiry, strike, option_type } = contract;
  return { exchange, underlying_symbol, expiry, strike, option_type };
}

export function DerivativesScanner() {
  const [catalog, setCatalog] = useState<{
    fields: Field[];
    max_underlyings: number;
  } | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [config, setConfig] = useState<Config>(initial);
  const [raw, setRaw] = useState("");
  const [lists, setLists] = useState<Watchlist[]>([]);
  const [members, setMembers] = useState<WatchDetail | null>(null);
  const [field, setField] = useState("");
  const [operator, setOperator] = useState("");
  const [value, setValue] = useState("");
  const [upper, setUpper] = useState("");
  const [selectedEnums, setSelectedEnums] = useState<string[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [selected, setSelected] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [sort, setSort] = useState("canonical");
  const [optionalColumns, setOptionalColumns] = useState<
    OptionalResultColumn[]
  >([]);
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [brokerId, setBrokerId] = useState("");
  const [ticket, setTicket] = useState<{
    account: Account;
    canonical: { contract: OptionContractRequest; side: Side };
  } | null>(null);
  const spec = catalog?.fields.find((f) => f.field === field);
  const broker = brokers.find((b) => b.account.id === brokerId);
  const activeRows =
    run?.rows.filter((r) => showAll || r.outcome === "MATCH") || [];
  const rows = [...activeRows].sort((a, b) => {
    const key = sort as keyof Row;
    if (sort === "canonical") return 0;
    if (
      [
        "ltp",
        "volume",
        "open_interest",
        "change_in_open_interest",
        "spread_percent",
        "implied_volatility",
      ].includes(sort)
    )
      return (
        Number(
          a.market[sort as keyof OptionMarketSnapshot] ??
            Number.POSITIVE_INFINITY,
        ) -
        Number(
          b.market[sort as keyof OptionMarketSnapshot] ??
            Number.POSITIVE_INFINITY,
        )
      );
    if (
      [
        "volume_percentile",
        "volume_vs_chain_median",
        "volume_oi_percent",
      ].includes(sort)
    )
      return (
        Number(
          a[
            sort as
              | "volume_percentile"
              | "volume_vs_chain_median"
              | "volume_oi_percent"
          ] ?? Number.POSITIVE_INFINITY,
        ) -
        Number(
          b[
            sort as
              | "volume_percentile"
              | "volume_vs_chain_median"
              | "volume_oi_percent"
          ] ?? Number.POSITIVE_INFINITY,
        )
      );
    if (sort === "dte") return a.dte - b.dte;
    if (sort === "strike") return Number(a.strike) - Number(b.strike);
    return String(a[key]).localeCompare(String(b[key]));
  });

  useEffect(() => {
    let active = true;
    void scannerApi<{ fields: Field[]; max_underlyings: number }>(
      "derivatives/catalog",
    )
      .then((response) => {
        if (!Array.isArray(response.fields)) {
          throw new Error("Invalid derivatives filter catalog");
        }
        if (active) {
          setCatalog(response.fields.length ? response : null);
          setCatalogError(
            response.fields.length ? "" : "No derivative filters available.",
          );
        }
      })
      .catch(() => {
        if (active) {
          setCatalog(null);
          setCatalogError("Derivatives filter catalog could not be loaded.");
        }
      });
    return () => {
      active = false;
    };
  }, [catalogRetry]);
  useEffect(() => {
    void scannerApi<Run[]>("derivatives/runs")
      .then(setHistory)
      .catch(() => setError("Recent derivatives scans could not be loaded."));
    void scannerApi<Saved[]>("derivatives/saved")
      .then(setSaved)
      .catch(() => setError("Saved derivatives scans could not be loaded."));
    void watchApi<Watchlist[]>("")
      .then((w) =>
        setLists(w.filter((x) => !x.archived && x.enabled !== false)),
      )
      .catch(() => setError("Watchlists could not be loaded."));
    void brokerApi<Account[]>("accounts")
      .then(async (accounts) => {
        const capable = await Promise.all(
          accounts
            .filter((a) => a.state === "connected")
            .map(async (account) => {
              try {
                const capability = await brokerApi<Capability>(
                  `accounts/${account.id}/order-entry/capabilities`,
                );
                return capability.enabled && capability.broker.supports_options
                  ? { account, capability }
                  : null;
              } catch {
                return null;
              }
            }),
        );
        const valid = capable.filter((b): b is Broker => b !== null);
        setBrokers(valid);
        if (valid.length === 1) setBrokerId(valid[0].account.id);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (config.universe.source !== "WATCHLIST" || !config.universe.watchlist_id)
      return;
    let active = true;
    void watchApi<WatchDetail>(`/${config.universe.watchlist_id}`)
      .then((detail) => {
        if (active) setMembers(detail);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [config.universe.source, config.universe.watchlist_id]);

  function editField(next: string) {
    const info = catalog?.fields.find((f) => f.field === next);
    setField(next);
    setOperator(
      info?.kind === "enum" || info?.kind === "multi" ? "equals" : ">=",
    );
    setValue(info?.values?.[0] || "");
    setUpper("");
    setSelectedEnums(info?.values ? [info.values[0]] : []);
  }
  function addFilter() {
    if (!spec) return;
    let next: Filter;
    if (spec.kind === "multi") {
      if (!selectedEnums.length) {
        setError("Choose at least one moneyness value.");
        return;
      }
      next = { field, operator, value: selectedEnums };
    } else if (spec.kind === "enum") next = { field, operator, value };
    else {
      const lower = Number(value),
        high = Number(upper);
      if (
        value.trim() === "" ||
        !Number.isFinite(lower) ||
        (operator === "between" &&
          (upper.trim() === "" || !Number.isFinite(high) || lower > high))
      ) {
        setError("Enter a valid numeric value or ordered range.");
        return;
      }
      if (
        spec.kind === "integer" &&
        (!Number.isInteger(lower) ||
          (operator === "between" && !Number.isInteger(high)))
      ) {
        setError("This field needs whole numbers.");
        return;
      }
      if (
        (spec.minimum !== undefined &&
          (lower < spec.minimum ||
            (operator === "between" && high < spec.minimum))) ||
        (spec.maximum !== undefined &&
          (lower > spec.maximum ||
            (operator === "between" && high > spec.maximum)))
      ) {
        setError("Value is outside the field range.");
        return;
      }
      next = {
        field,
        operator,
        value: operator === "between" ? [lower, high] : lower,
      };
    }
    setConfig((c) => ({
      ...c,
      filters: [...c.filters.filter((f) => f.field !== field), next],
    }));
    setError("");
  }
  async function execute() {
    const symbols =
      config.universe.source === "CUSTOM"
        ? parseSymbols(raw)
        : config.universe.symbols;
    if (symbols.length < 1 || symbols.length > 5) {
      setError("Select 1 to 5 underlyings. Nothing was truncated.");
      return;
    }
    if (!config.filters.length) {
      setError("Add at least one active filter before scanning.");
      return;
    }
    const submitted = { ...config, universe: { ...config.universe, symbols } };
    setBusy(true);
    setError("");
    setSelected(null);
    try {
      const next = await scannerApi<Run>("derivatives/runs", "POST", submitted);
      setRun(next);
      setHistory((h) => [next, ...h]);
      setNotice(`Scan complete: ${next.counts.matches} matching contracts.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    try {
      const symbols =
        config.universe.source === "CUSTOM"
          ? parseSymbols(raw)
          : config.universe.symbols;
      if (!symbols.length || symbols.length > 5 || !config.filters.length) {
        setError(
          "Choose 1 to 5 underlyings and at least one filter before saving.",
        );
        return;
      }
      const name = window.prompt("Saved scan name", config.name)?.trim();
      if (!name) return;
      const next = await scannerApi<Saved>("derivatives/saved", "POST", {
        config: { ...config, name, universe: { ...config.universe, symbols } },
        archived: false,
      });
      setSaved((s) => [next, ...s]);
      setNotice("Derivatives scan saved.");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function load(savedConfig: Config) {
    setConfig(savedConfig);
    setRaw(savedConfig.universe.symbols.join(", "));
    setRun(null);
    setSelected(null);
    setNotice("Saved setup loaded. Review it before running.");
  }
  async function view(key: string) {
    try {
      const next = await scannerApi<Run>(`derivatives/runs/${key}`);
      setRun(next);
      setSelected(null);
      setShowAll(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function openTrade(side: Side) {
    if (!selected || !broker) return;
    if (expiredContract(selected.contract)) {
      setError(
        "This historical contract has expired and cannot be sent to Broker V2.",
      );
      return;
    }
    setTicket({
      account: broker.account,
      canonical: { contract: tradeContract(selected.contract), side },
    });
  }
  return (
    <div
      className="derivative-scanner"
      role="tabpanel"
      aria-label="Derivatives Scanner"
    >
      {error && (
        <div className="wl-error" role="alert">
          {error}
          <button onClick={() => setError("")} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}
      {notice && (
        <div className="wl-toast" role="status">
          {notice}
          <button onClick={() => setNotice("")} aria-label="Dismiss notice">
            ×
          </button>
        </div>
      )}
      <div className="derivative-actions wl-card">
        <strong>Single-leg NSE options · Dhan market data</strong>
        <span>Up to 5 underlyings · ±5–20 strikes · no ranking</span>
        <button onClick={() => void save()}>Save Scan</button>
        <a href="#derivative-saved">My Scans</a>
        <a href="#derivative-history">Scan History</a>
      </div>
      <div
        className={`sc-grid conditional-detail-layout${selected ? " has-detail" : ""}`}
      >
        <aside className="wl-card sc-builder derivative-builder">
          <h2>Build an options scan</h2>
          <p>
            Select up to 5 optionable underlyings, choose expiry and add
            explicit filters.
          </p>
          <div className="sc-universe-tabs">
            <button
              aria-pressed={config.universe.source === "CUSTOM"}
              onClick={() =>
                setConfig((c) => ({
                  ...c,
                  universe: { source: "CUSTOM", symbols: [] },
                }))
              }
            >
              Custom
            </button>
            <button
              aria-pressed={config.universe.source === "WATCHLIST"}
              onClick={() =>
                setConfig((c) => ({
                  ...c,
                  universe: { source: "WATCHLIST", symbols: [] },
                }))
              }
            >
              Watchlist
            </button>
          </div>
          {config.universe.source === "CUSTOM" ? (
            <label className="sc-label">
              NSE underlyings
              <textarea
                rows={3}
                value={raw}
                onChange={(e) => setRaw(e.target.value)}
                placeholder="NIFTY, BANKNIFTY, RELIANCE"
              />
            </label>
          ) : (
            <>
              <label className="sc-label">
                Watchlist
                <select
                  value={config.universe.watchlist_id || ""}
                  onChange={(e) => {
                    setMembers(null);
                    setConfig((c) => ({
                      ...c,
                      universe: {
                        source: "WATCHLIST",
                        watchlist_id: e.target.value,
                        symbols: [],
                      },
                    }));
                  }}
                >
                  <option value="">Choose watchlist</option>
                  {lists.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name} ({l.count})
                    </option>
                  ))}
                </select>
              </label>
              <div className="sc-members">
                {members?.items.map((item) => (
                  <label key={item.instrument.instrument_id}>
                    <input
                      type="checkbox"
                      checked={config.universe.symbols.includes(
                        item.instrument.symbol,
                      )}
                      onChange={(e) => {
                        const symbol = item.instrument.symbol;
                        setConfig((c) => ({
                          ...c,
                          universe: {
                            ...c.universe,
                            symbols: e.target.checked
                              ? [...c.universe.symbols, symbol]
                              : c.universe.symbols.filter((s) => s !== symbol),
                          },
                        }));
                      }}
                    />
                    {item.instrument.symbol}
                  </label>
                ))}
              </div>
            </>
          )}
          <small>
            {config.universe.source === "CUSTOM"
              ? parseSymbols(raw).length
              : config.universe.symbols.length}{" "}
            selected · maximum 5; excess selection is rejected, never truncated.
          </small>
          <label className="sc-label">
            Expiry policy
            <select
              value={config.expiry_mode}
              onChange={(e) =>
                setConfig((c) => ({
                  ...c,
                  expiry_mode: e.target.value as Config["expiry_mode"],
                }))
              }
            >
              <option value="NEAREST">Nearest active</option>
              <option value="EXACT">Exact expiry</option>
            </select>
          </label>
          {config.expiry_mode === "EXACT" && (
            <label className="sc-label">
              Exact expiry (IST)
              <input
                type="date"
                value={config.exact_expiry || ""}
                onChange={(e) =>
                  setConfig((c) => ({
                    ...c,
                    exact_expiry: e.target.value || null,
                  }))
                }
              />
            </label>
          )}
          <label className="sc-label">
            Strikes around ATM
            <select
              value={config.strike_window}
              onChange={(e) =>
                setConfig((c) => ({
                  ...c,
                  strike_window: Number(
                    e.target.value,
                  ) as Config["strike_window"],
                }))
              }
            >
              {[5, 10, 15, 20].map((n) => (
                <option key={n} value={n}>
                  ±{n}
                </option>
              ))}
            </select>
          </label>
          <h3>Active filters</h3>
          {config.filters.length ? (
            <div className="derivative-chips">
              {config.filters.map((f) => (
                <button
                  key={f.field}
                  onClick={() =>
                    setConfig((c) => ({
                      ...c,
                      filters: c.filters.filter((x) => x.field !== f.field),
                    }))
                  }
                  aria-label={`Remove ${filterText(f, catalog?.fields || [])}`}
                >
                  {filterText(f, catalog?.fields || [])} ×
                </button>
              ))}
            </div>
          ) : (
            <p>No active filters. Draft values do not run.</p>
          )}
          <h3>Add / edit filter</h3>
          {catalogError && (
            <div className="wl-error" role="alert">
              {catalogError}{" "}
              <button onClick={() => setCatalogRetry((attempt) => attempt + 1)}>
                Retry
              </button>
            </div>
          )}
          <label className="sc-label">
            Field
            <select
              value={spec ? field : ""}
              disabled={!catalog}
              onChange={(e) => editField(e.target.value)}
            >
              <option value="">
                {catalog ? "Select field" : "Filters unavailable"}
              </option>
              {catalog &&
                [...new Set(catalog.fields.map((f) => f.category))].map(
                  (category) => (
                    <optgroup key={category} label={category}>
                      {catalog.fields
                        .filter((f) => f.category === category)
                        .map((f) => (
                          <option key={f.field} value={f.field}>
                            {f.label}
                            {f.provider_dependent
                              ? " (provider-dependent)"
                              : ""}
                          </option>
                        ))}
                    </optgroup>
                  ),
                )}
            </select>
          </label>
          <label className="sc-label">
            Comparison
            <select
              value={spec?.operators.includes(operator) ? operator : ""}
              disabled={!spec}
              onChange={(e) => setOperator(e.target.value)}
            >
              {!spec && <option value="">Choose a field first</option>}
              {spec?.operators.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </select>
          </label>
          {spec?.kind === "multi" ? (
            <fieldset>
              <legend>Moneyness</legend>
              {spec.values?.map((v) => (
                <label key={v}>
                  <input
                    type="checkbox"
                    checked={selectedEnums.includes(v)}
                    onChange={(e) =>
                      setSelectedEnums((xs) =>
                        e.target.checked
                          ? [...xs, v]
                          : xs.filter((x) => x !== v),
                      )
                    }
                  />
                  {v}
                </label>
              ))}
            </fieldset>
          ) : spec?.kind === "enum" ? (
            <label className="sc-label">
              Value
              <select value={value} onChange={(e) => setValue(e.target.value)}>
                {spec.values?.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          ) : (
            <>
              <label className="sc-label">
                {operator === "between" ? "Lower bound" : "Value"}
                <input
                  type="number"
                  step={spec?.kind === "integer" ? "1" : "any"}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
              </label>
              {operator === "between" && (
                <label className="sc-label">
                  Upper bound
                  <input
                    type="number"
                    step={spec?.kind === "integer" ? "1" : "any"}
                    value={upper}
                    onChange={(e) => setUpper(e.target.value)}
                  />
                </label>
              )}
            </>
          )}
          {spec &&
            [
              "volume_percentile",
              "volume_vs_chain_median",
              "volume_oi_percent",
            ].includes(spec.field) && (
              <small>
                Relative volume uses CE and PE contracts from this underlying
                and expiry&apos;s bounded chain. Missing observations cannot
                pass an active filter.
              </small>
            )}
          {spec?.provider_dependent && (
            <small>
              This field can be unavailable in the current Dhan chain; an active
              filter cannot pass missing data.
            </small>
          )}
          <button onClick={addFilter} disabled={!spec}>
            Add / update filter
          </button>
          <div className="derivative-run">
            <button
              className="wl-primary"
              disabled={busy}
              onClick={() => void execute()}
            >
              {busy ? "Scanning…" : "Run Scan"}
            </button>
            <button
              onClick={() => {
                setConfig(initial);
                setRaw("");
                editField("");
                setRun(null);
                setSelected(null);
              }}
            >
              Reset
            </button>
          </div>
          <small>
            O2 chain snapshots · Dhan completed bars for underlying technical
            filters. No synthetic fallback.
          </small>
        </aside>
        <main className="sc-center">
          <section className="wl-card derivative-results">
            <div className="derivative-results-head">
              <div>
                <h2>Scan Results</h2>
                <small>
                  {run
                    ? `${run.counts.matches} matches · ${new Date(run.created_at).toLocaleString("en-IN")}`
                    : "Build your next scan"}
                </small>
              </div>
              {run && (
                <div>
                  <label>
                    <input
                      type="checkbox"
                      checked={showAll}
                      onChange={(e) => setShowAll(e.target.checked)}
                    />{" "}
                    Show non-matches / not evaluated
                  </label>
                  <details className="derivative-columns">
                    <summary>Columns</summary>
                    {optionalResultColumns.map(([key, label]) => (
                      <label key={key}>
                        <input
                          type="checkbox"
                          checked={optionalColumns.includes(key)}
                          onChange={(e) =>
                            setOptionalColumns((current) =>
                              e.target.checked
                                ? [...current, key]
                                : current.filter((column) => column !== key),
                            )
                          }
                        />
                        {label}
                      </label>
                    ))}
                  </details>
                  <label>
                    {" "}
                    Sort{" "}
                    <select
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      {[
                        ["canonical", "Canonical"],
                        ["underlying", "Underlying"],
                        ["dte", "DTE"],
                        ["strike", "Strike"],
                        ["ltp", "LTP"],
                        ["volume", "Volume"],
                        ["volume_percentile", "Vol Pctl"],
                        ["volume_vs_chain_median", "Vol/Median"],
                        ["volume_oi_percent", "Vol/OI %"],
                        ["open_interest", "OI"],
                        ["change_in_open_interest", "ΔOI"],
                        ["spread_percent", "Spread %"],
                        ["implied_volatility", "IV"],
                      ].map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </div>
            {run ? (
              <>
                <div className="derivative-counts">
                  {[
                    ["requested", "Underlyings requested"],
                    ["resolved", "Resolved"],
                    ["chains_evaluated", "Chains"],
                    ["contracts_evaluated", "Contracts evaluated"],
                    ["not_evaluated", "Not evaluated"],
                    ["matches", "Matches"],
                  ].map(([key, label]) => (
                    <div key={key}>
                      <small>{label}</small>
                      <strong>{run.counts[key]}</strong>
                    </div>
                  ))}
                </div>
                <div
                  className="derivative-table-wrap"
                  role="region"
                  aria-label="Option scan results, scroll horizontally if needed"
                  tabIndex={0}
                >
                  <table>
                    <thead>
                      <tr>
                        {[
                          "Underlying",
                          "Spot",
                          "Expiry",
                          "DTE",
                          "Strike",
                          "Type",
                          "Money",
                          "LTP",
                          "Volume",
                          "Vol Pctl",
                          "OI",
                          "ΔOI",
                          "Spread %",
                          "IV",
                          "Trend",
                          ...optionalResultColumns
                            .filter(([key]) => optionalColumns.includes(key))
                            .map(([, label]) => label),
                          "Reason",
                          "Actions",
                        ].map((h) => (
                          <th key={h} title={resultColumnHelp[h]}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr
                          key={row.contract.canonical_id}
                          className={
                            selected?.contract.canonical_id ===
                            row.contract.canonical_id
                              ? "derivative-selected"
                              : ""
                          }
                        >
                          <td>{row.underlying}</td>
                          <td>{num(row.spot)}</td>
                          <td>{expiryLabel(row.expiry)}</td>
                          <td>{row.dte}</td>
                          <td>{num(row.strike)}</td>
                          <td>{row.option_type}</td>
                          <td>{row.moneyness || "—"}</td>
                          <td>{num(row.market.ltp)}</td>
                          <td>{num(row.market.volume)}</td>
                          <td title="Volume percentile within the same underlying and expiry chain">
                            {row.volume_percentile == null
                              ? "—"
                              : num(row.volume_percentile)}
                          </td>
                          <td>{num(row.market.open_interest)}</td>
                          <td>{num(row.market.change_in_open_interest)}</td>
                          <td>{num(row.market.spread_percent)}</td>
                          <td>{num(row.market.implied_volatility)}</td>
                          <td>{row.technical.trend || "—"}</td>
                          {optionalResultColumns
                            .filter(([key]) => optionalColumns.includes(key))
                            .map(([key]) => (
                              <td key={key}>{optionalResultValue(row, key)}</td>
                            ))}
                          <td>{row.reason}</td>
                          <td>
                            <button onClick={() => setSelected(row)}>
                              Why?
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div
                  className="derivative-mobile-cards"
                  aria-label="Option scan result cards"
                >
                  {rows.map((row) => (
                    <article
                      key={row.contract.canonical_id}
                      className={
                        selected?.contract.canonical_id ===
                        row.contract.canonical_id
                          ? "derivative-mobile-card derivative-selected"
                          : "derivative-mobile-card"
                      }
                    >
                      <header>
                        <strong>
                          {row.underlying} {num(row.strike)} {row.option_type}
                        </strong>
                        <span>{row.moneyness || "—"}</span>
                      </header>
                      <div className="derivative-mobile-facts">
                        <span>
                          <small>LTP</small>
                          <b>{num(row.market.ltp)}</b>
                        </span>
                        <span>
                          <small>Expiry</small>
                          <b>{expiryLabel(row.expiry)}</b>
                        </span>
                        <span>
                          <small>DTE</small>
                          <b>{row.dte}</b>
                        </span>
                      </div>
                      <p>
                        Vol Pctl {num(row.volume_percentile)} · Vol/Median{" "}
                        {row.volume_vs_chain_median == null
                          ? "—"
                          : `${num(row.volume_vs_chain_median)}x`}{" "}
                        · Vol/OI{" "}
                        {row.volume_oi_percent == null
                          ? "—"
                          : `${num(row.volume_oi_percent)}%`}
                      </p>
                      <p>{row.reason}</p>
                      <button onClick={() => setSelected(row)}>Why?</button>
                    </article>
                  ))}
                </div>
                {rows.length === 0 && (
                  <p>
                    {run.counts.matches
                      ? "No results in this view."
                      : "No contracts matched these filters. No result was invented."}
                  </p>
                )}
                {run.underlyings.some(
                  (u) => u.outcome === "NOT_EVALUATED" || u.technical_failure,
                ) && (
                  <details>
                    <summary>Underlying diagnostics</summary>
                    <ul>
                      {run.underlyings.map((u) => (
                        <li key={u.symbol}>
                          {u.symbol}:{" "}
                          {u.failure || u.technical_failure || u.outcome}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <small>
                  Option market data: Dhan · Underlying technicals: Dhan
                  completed daily bars · Metadata: local DB. Snapshot freshness
                  is shown in details.
                </small>
              </>
            ) : (
              <p>
                Select underlyings, expiry and at least one filter, then Run
                Scan.
              </p>
            )}
          </section>
          <div className="derivative-history-grid">
            <section className="wl-card" id="derivative-saved">
              <h3>Saved Scans</h3>
              {saved
                .filter((s) => !s.archived)
                .map((s) => (
                  <div key={s.id} className="derivative-history-item">
                    <strong>{s.config.name}</strong>
                    <button onClick={() => load(s.config)}>Use setup</button>
                  </div>
                ))}
              {!saved.length && <p>No saved derivatives scans yet.</p>}
            </section>
            <section className="wl-card" id="derivative-history">
              <h3>Recent Scans</h3>
              {history.slice(0, 10).map((h) => (
                <div key={h.id} className="derivative-history-item">
                  <span>
                    {h.config.name} · {h.counts.matches} matches ·{" "}
                    {new Date(h.created_at).toLocaleString("en-IN")}
                  </span>
                  <button onClick={() => void view(h.id)}>View</button>
                </div>
              ))}
              {!history.length && <p>No derivatives scan history yet.</p>}
            </section>
          </div>
        </main>
        {selected && (
          <aside
            className="wl-card derivative-detail"
            aria-label="Selected option contract"
          >
            <button
              className="detail-panel-clear"
              onClick={() => setSelected(null)}
            >
              Close details
            </button>
            <h2>{selected.contract.display_symbol}</h2>
            <p>{selected.contract.canonical_id}</p>
            <dl>
              <dt>Contract</dt>
              <dd>
                {selected.underlying} · {expiryLabel(selected.expiry)} ·{" "}
                {num(selected.strike)} {selected.option_type}
              </dd>
              <dt>Spot / moneyness</dt>
              <dd>
                {num(selected.spot)} · {selected.moneyness || "Unavailable"}
              </dd>
              <dt>Market data</dt>
              <dd>
                LTP {num(selected.market.ltp)} · Bid {num(selected.market.bid)}{" "}
                · Ask {num(selected.market.ask)}
              </dd>
              <dt>Liquidity / Activity</dt>
              <dd>
                Volume {num(selected.market.volume)} · Spread{" "}
                {num(selected.market.spread_percent)}%
              </dd>
              <dt>Volume percentile</dt>
              <dd>{num(selected.volume_percentile)}</dd>
              <dt>Chain median volume</dt>
              <dd>{num(selected.volume_chain_median)}</dd>
              <dt>Volume vs median</dt>
              <dd>
                {selected.volume_vs_chain_median == null
                  ? "—"
                  : `${num(selected.volume_vs_chain_median)}x`}
              </dd>
              <dt>Volume / OI</dt>
              <dd>
                {selected.volume_oi_percent == null
                  ? "—"
                  : `${num(selected.volume_oi_percent)}%`}
              </dd>
              <dt>Comparison cohort</dt>
              <dd>
                {selected.underlying} · {expiryLabel(selected.expiry)} ·{" "}
                {selected.relative_volume_cohort_size ?? "—"} valid CE + PE
                volumes in the bounded chain
              </dd>
              <dt>Open interest</dt>
              <dd>
                OI {num(selected.market.open_interest)} · ΔOI{" "}
                {num(selected.market.change_in_open_interest)}
              </dd>
              <dt>Volatility / Greeks</dt>
              <dd>
                IV {num(selected.market.implied_volatility)} · Delta{" "}
                {num(selected.market.delta)} · Theta{" "}
                {num(selected.market.theta)}
              </dd>
              <dt>Underlying technical</dt>
              <dd>
                Trend {selected.technical.trend || "—"} · RSI{" "}
                {num(selected.technical.rsi as number | null)} · Supertrend{" "}
                {selected.technical.supertrend || "—"}
              </dd>
              <dt>Sector / market cap</dt>
              <dd>
                {selected.instrument_metadata?.sector || "Unavailable"} ·{" "}
                {selected.instrument_metadata?.market_cap_category ||
                  "Unavailable"}
              </dd>
            </dl>
            <h3>
              Why{" "}
              {selected.outcome === "MATCH"
                ? "matched"
                : selected.outcome.toLowerCase().replace("_", " ")}
            </h3>
            <ul className="derivative-diagnostics">
              {selected.diagnostics.map((d) => (
                <li key={d.filter.field}>
                  {d.passed === true ? "✓" : d.passed === false ? "✕" : "?"}{" "}
                  {filterText(d.filter, catalog?.fields || [])}
                  <small>Observed: {diagnosticObserved(d)}</small>
                </li>
              ))}
            </ul>
            {selected.missing_evidence.length > 0 && (
              <p>Missing evidence: {selected.missing_evidence.join(", ")}</p>
            )}
            {selected.warnings.length > 0 && (
              <p>Warnings: {selected.warnings.join(", ")}</p>
            )}
            <h3>Provenance</h3>
            <p>
              Dhan · {selected.provenance.market_source} ·{" "}
              {selected.provenance.freshness}
              {selected.provenance.cached ? " · cached" : " · retrieved"}
            </p>
            <small>
              Source time: {selected.provenance.source_time || "Unavailable"}
              <br />
              Retrieved: {selected.provenance.received_at}
            </small>
            <div className="derivative-detail-actions">
              <Link
                href={`/options-analytics?underlying=${encodeURIComponent(selected.underlying)}&expiry=${encodeURIComponent(selected.expiry)}&contract_id=${encodeURIComponent(selected.contract.canonical_id)}&strike=${encodeURIComponent(selected.strike)}&side=${selected.option_type}`}
              >
                Open in Options Analytics
              </Link>
              <label>
                Broker
                <select
                  value={brokerId}
                  onChange={(e) => setBrokerId(e.target.value)}
                >
                  <option value="">Select broker</option>
                  {brokers.map((b) => (
                    <option key={b.account.id} value={b.account.id}>
                      {b.account.name}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={!broker || expiredContract(selected.contract)}
                onClick={() => openTrade("BUY")}
              >
                Buy · Broker V2 preview
              </button>
              <button
                disabled={!broker || expiredContract(selected.contract)}
                onClick={() => openTrade("SELL")}
              >
                Sell · Broker V2 preview
              </button>
            </div>
            <small>
              Broker preview requires separate confirmation. Expired historical
              contracts cannot be traded.
            </small>
          </aside>
        )}
      </div>
      {ticket && (
        <OrderTicket
          account={ticket.account}
          canonical={ticket.canonical}
          close={() => setTicket(null)}
        />
      )}
    </div>
  );
}
