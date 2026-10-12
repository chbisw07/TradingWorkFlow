"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { OrderTicket } from "../brokers/order-ticket";
import { brokerApi, type Account } from "../../lib/brokers";
import type { Capability, Side } from "../../lib/broker-orders";
import type {
  OptionContract,
  OptionContractRequest,
  OptionMarketSnapshot,
} from "../../lib/options";
import { chainNumber as num, expiryLabel } from "../../lib/option-chain-client";
import {
  scannerApi,
  initialConfig,
  type ProviderResults,
} from "../../lib/scanner";
import { ScannerHistoryMenu } from "./scanner-history-menu";
import { ScannerColumnsMenu } from "./scanner-columns-menu";
import { ScannerWatchlistSelector } from "./watchlist-selector";
import { watchApi, changeText, type Watchlist } from "../../lib/watchlists";

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
  oi_percentile?: number | null;
  oi_chain_median?: number | null;
  oi_vs_chain_median?: number | null;
  oi_change_percent?: number | null;
  oi_change_percentile?: number | null;
  relative_oi_cohort_size?: number;
  oi_interpretation?: {
    label: string;
    inferred: boolean;
    confidence: "LOW" | "MEDIUM" | "HIGH" | "INSUFFICIENT";
    freshness: string;
    window_start: string | null;
    window_end: string;
    window_seconds: number | null;
    premium_change_percent: number | null;
    oi_window_change_percent: number | null;
    underlying_change_percent: number | null;
    iv_change_points: number | null;
    reason: string;
  };
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
const resultColumnOptions = [
  ["underlying", "Underlying"],
  ["expiry", "Expiry"],
  ["strike", "Strike"],
  ["option_type", "Type"],
  ["ltp", "LTP"],
  ["volume", "Volume"],
  ["volume_percentile", "Vol Pctl"],
  ["open_interest", "OI"],
  ["oi_percentile", "OI Pctl"],
  ["change_in_open_interest", "ΔOI"],
  ["oi_change_percent", "ΔOI %"],
  ["implied_volatility", "IV"],
  ["trend", "Trend"],
  ["oi_interpretation", "OI Interpretation (Inferred)"],
  ["spot", "Spot"],
  ["dte", "DTE"],
  ["moneyness", "Money"],
  ["spread_percent", "Spread %"],
  ["oi_vs_chain_median", "OI vs Median"],
  ["oi_change_percentile", "ΔOI Percentile"],
  ["volume_vs_chain_median", "Vol/Median"],
  ["volume_oi_percent", "Vol/OI %"],
  ["bid", "Bid"],
  ["ask", "Ask"],
  ["strike_distance_percent", "Strike distance %"],
  ["delta", "Delta"],
  ["gamma", "Gamma"],
  ["theta", "Theta"],
  ["vega", "Vega"],
  ["rsi", "Underlying RSI"],
  ["sector", "Sector"],
  ["reason", "Reason"],
] as const;
type ResultColumn = (typeof resultColumnOptions)[number][0];
const defaultResultColumns: ResultColumn[] = resultColumnOptions
  .slice(0, 14)
  .map(([key]) => key);
function signed(value: number | string | null | undefined, unit = ""): string {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n > 0 ? "+" : ""}${num(n)}${unit}`;
}
function oiEvidenceText(row: Row): string {
  const evidence = row.oi_interpretation;
  if (!evidence)
    return "Inferred, not proven. Historical interpretation unavailable.";
  return [
    "Inferred, not proven",
    `Premium ${signed(evidence.premium_change_percent, "%")}`,
    `OI ${signed(evidence.oi_window_change_percent, "%")}`,
    `Underlying ${signed(evidence.underlying_change_percent, "%")}`,
    `IV ${signed(evidence.iv_change_points, " pp")}`,
    `Window ${evidence.window_seconds == null ? "unavailable" : `${num(evidence.window_seconds)} seconds`}`,
    `Freshness ${evidence.freshness}`,
    evidence.reason,
  ].join(" · ");
}
function OiBadge({ row }: { row: Row }) {
  const label = row.oi_interpretation?.label || "Insufficient evidence";
  const tone = label.includes("long buildup")
    ? "long"
    : label.includes("short buildup")
      ? "short"
      : label === "Short covering"
        ? "covering"
        : label === "Long unwinding"
          ? "unwinding"
          : "neutral";
  return (
    <span
      className={`derivative-oi-badge derivative-oi-${tone}`}
      title={oiEvidenceText(row)}
      aria-label={`OI interpretation, inferred: ${label}. ${oiEvidenceText(row)}`}
      tabIndex={0}
    >
      {label} <small>Inferred</small>
    </span>
  );
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
  const unit = spec?.unit === "x" || spec?.unit === "%" ? spec.unit : "";
  return `${spec?.label || filter.field} ${filter.operator === "between" ? "between" : filter.operator} ${valueText(filter.value)}${unit || ""}`;
}
function diagnosticObserved(diagnostic: Diagnostic): string {
  if (diagnostic.observed == null) return "Unavailable";
  const suffix =
    diagnostic.filter.field === "volume_vs_chain_median" ||
    diagnostic.filter.field === "oi_vs_chain_median"
      ? "x"
      : [
            "volume_oi_percent",
            "oi_percentile",
            "oi_change_percent",
            "oi_change_percentile",
          ].includes(diagnostic.filter.field)
        ? "%"
        : "";
  return `${valueText(diagnostic.observed)}${suffix}`;
}
const resultColumnHelp: Record<string, string> = {
  "Vol Pctl": "Volume percentile within the same underlying and expiry chain",
  "Vol/Median": "Contract volume divided by the chain median volume",
  "Vol/OI %": "Contract volume as a percentage of current open interest",
  "OI Pctl": "OI percentile within this bounded underlying and expiry chain",
  "ΔOI %": "Signed change divided by prior OI; not a scan-to-scan movement",
  "OI Interpretation (Inferred)":
    "Candidate interpretation from comparable archived snapshots; not a signal",
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

type OptionTypeSelection = "CE" | "PE" | "BOTH";

function optionTypeFromFilters(filters: Filter[]): OptionTypeSelection {
  const filter = filters.find((item) => item.field === "option_type");
  if (!filter) return "BOTH";
  const value = Array.isArray(filter.value) ? filter.value[0] : filter.value;
  if (filter.operator === "not_equals") {
    if (value === "CE") return "PE";
    if (value === "PE") return "CE";
  }
  return value === "CE" || value === "PE" ? value : "BOTH";
}

function underlyingHref(row: Row): string {
  return `/options-analytics?underlying=${encodeURIComponent(row.contract.underlying_symbol)}`;
}

function analyticsHref(row: Row): string {
  return `/options-analytics?underlying=${encodeURIComponent(row.underlying)}&expiry=${encodeURIComponent(row.expiry)}&contract_id=${encodeURIComponent(row.contract.canonical_id)}&strike=${encodeURIComponent(row.strike)}&side=${row.option_type}`;
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
  const [optionability, setOptionability] = useState<{
    members: number;
    optionable: number;
    symbols: string[];
    max_underlyings: number;
  } | null>(null);
  const [customOpen, setCustomOpen] = useState(false);
  const [field, setField] = useState("");
  const [operator, setOperator] = useState("");
  const [value, setValue] = useState("");
  const [upper, setUpper] = useState("");
  const [selectedEnums, setSelectedEnums] = useState<string[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [selected, setSelected] = useState<Row | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [panelView, setPanelView] = useState<
    "detail" | "saved" | "recent" | "history" | "movers" | null
  >(null);
  const [toolbarHost, setToolbarHost] = useState<HTMLElement | null>(null);
  const [movers, setMovers] = useState<ProviderResults | null>(null);
  const [moverTab, setMoverTab] = useState("Top Gainers");
  const [moversBusy, setMoversBusy] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() =>
      setToolbarHost(document.getElementById("sc-derivative-toolbar")),
    );
    return () => cancelAnimationFrame(frame);
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [sort, setSort] = useState("canonical");
  const [visibleColumns, setVisibleColumns] =
    useState<ResultColumn[]>(defaultResultColumns);
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [brokerId, setBrokerId] = useState("");
  const [ticket, setTicket] = useState<{
    account: Account;
    canonical: { contract: OptionContractRequest; side: Side };
  } | null>(null);
  const spec = catalog?.fields.find((f) => f.field === field);
  const optionType = optionTypeFromFilters(config.filters);
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
        "oi_percentile",
        "oi_vs_chain_median",
        "oi_change_percent",
        "oi_change_percentile",
      ].includes(sort)
    )
      return (
        Number(
          a[
            sort as
              | "volume_percentile"
              | "volume_vs_chain_median"
              | "volume_oi_percent"
              | "oi_percentile"
              | "oi_vs_chain_median"
              | "oi_change_percent"
              | "oi_change_percentile"
          ] ?? Number.POSITIVE_INFINITY,
        ) -
        Number(
          b[
            sort as
              | "volume_percentile"
              | "volume_vs_chain_median"
              | "volume_oi_percent"
              | "oi_percentile"
              | "oi_vs_chain_median"
              | "oi_change_percent"
              | "oi_change_percentile"
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
    const id = config.universe.watchlist_id;
    void scannerApi<{
      members: number;
      optionable: number;
      symbols: string[];
      max_underlyings: number;
    }>(`derivatives/watchlists/${id}/optionable`)
      .then((projection) => {
        if (!active) return;
        setOptionability(projection);
        setConfig((current) =>
          current.universe.source === "WATCHLIST" &&
          current.universe.watchlist_id === id &&
          !current.universe.symbols.length
            ? {
                ...current,
                universe: {
                  ...current.universe,
                  symbols: projection.symbols.slice(0, 5),
                },
              }
            : current,
        );
      })
      .catch((reason: Error) => {
        if (active) {
          setOptionability(null);
          setError(`Watchlist optionability unavailable: ${reason.message}`);
        }
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
  function selectOptionType(next: OptionTypeSelection) {
    setConfig((current) => ({
      ...current,
      filters: [
        ...current.filters.filter((item) => item.field !== "option_type"),
        { field: "option_type", operator: "equals", value: next },
      ],
    }));
    editField("");
    setError("");
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
    setChecked([]);
    setPanelView(null);
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
    setOptionability(null);
    setConfig(savedConfig);
    setRaw(savedConfig.universe.symbols.join(", "));
    setRun(null);
    setSelected(null);
    setChecked([]);
    editField("");
    setNotice("Saved setup loaded. Review it before running.");
  }
  async function view(key: string) {
    try {
      const next = await scannerApi<Run>(`derivatives/runs/${key}`);
      setRun(next);
      setSelected(null);
      setChecked([]);
      setShowAll(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function openTrade(row: Row, side: Side) {
    if (!broker) return;
    if (expiredContract(row.contract)) {
      setError(
        "This historical contract has expired and cannot be sent to Broker V2.",
      );
      return;
    }
    setTicket({
      account: broker.account,
      canonical: { contract: tradeContract(row.contract), side },
    });
  }
  const selectedForAction = rows.find(
    (row) => row.contract.canonical_id === checked[0],
  );
  const tradeUnavailable = !broker
    ? "Select an options-capable broker in Instrument Analysis"
    : "Expired contracts cannot be traded";
  function rowActions(row: Row) {
    return (
      <div className="sc-row-actions derivative-row-actions">
        <button
          aria-label="Why?"
          onClick={() => {
            setSelected(row);
            setPanelView("detail");
          }}
        >
          Why?
        </button>
        <Link
          href={analyticsHref(row)}
          aria-label={`Open ${row.contract.display_symbol} in Options Analytics`}
          title="Open exact contract in Options Analytics"
        >
          Analytics
        </Link>
        <button
          className="wl-buy"
          aria-label={`Buy ${row.contract.display_symbol}`}
          title={
            !broker || expiredContract(row.contract)
              ? tradeUnavailable
              : "Broker V2 preview"
          }
          disabled={!broker || expiredContract(row.contract)}
          onClick={() => openTrade(row, "BUY")}
        >
          B
        </button>
        <button
          className="wl-sell"
          aria-label={`Sell ${row.contract.display_symbol}`}
          title={
            !broker || expiredContract(row.contract)
              ? tradeUnavailable
              : "Broker V2 preview"
          }
          disabled={!broker || expiredContract(row.contract)}
          onClick={() => openTrade(row, "SELL")}
        >
          S
        </button>
      </div>
    );
  }
  function resultCell(row: Row, column: ResultColumn) {
    switch (column) {
      case "underlying":
        return (
          <Link
            className="derivative-underlying-link"
            href={underlyingHref(row)}
            aria-label={`Open ${row.contract.underlying_symbol} in Options Analytics`}
          >
            {row.underlying}
          </Link>
        );
      case "expiry":
        return expiryLabel(row.expiry);
      case "strike":
        return num(row.strike);
      case "option_type":
        return row.option_type;
      case "spot":
        return num(row.spot);
      case "dte":
        return row.dte;
      case "moneyness":
        return row.moneyness || "—";
      case "volume_percentile":
      case "oi_percentile":
      case "oi_change_percentile":
        return (
          <span className="derivative-percentile">{num(row[column])}</span>
        );
      case "oi_vs_chain_median":
      case "volume_vs_chain_median":
        return row[column] == null ? "—" : `${num(row[column])}x`;
      case "volume_oi_percent":
        return row.volume_oi_percent == null
          ? "—"
          : `${num(row.volume_oi_percent)}%`;
      case "oi_change_percent":
        return (
          <span
            className={
              row.oi_change_percent == null
                ? undefined
                : Number(row.oi_change_percent) >= 0
                  ? "derivative-positive"
                  : "derivative-negative"
            }
          >
            {signed(row.oi_change_percent, "%")}
          </span>
        );
      case "change_in_open_interest":
        return (
          <span
            className={
              row.market.change_in_open_interest == null
                ? undefined
                : Number(row.market.change_in_open_interest) >= 0
                  ? "derivative-positive"
                  : "derivative-negative"
            }
          >
            {signed(row.market.change_in_open_interest)}
          </span>
        );
      case "trend":
        return row.technical.trend || "—";
      case "oi_interpretation":
        return <OiBadge row={row} />;
      case "rsi":
        return num(row.technical.rsi);
      case "sector":
        return row.instrument_metadata?.sector || "—";
      case "strike_distance_percent":
        return num(row.strike_distance_percent);
      case "reason":
        return row.reason;
      case "ltp":
      case "volume":
      case "open_interest":
      case "implied_volatility":
      case "spread_percent":
      case "bid":
      case "ask":
      case "delta":
      case "gamma":
      case "theta":
      case "vega":
        return num(row.market[column]);
    }
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
      {toolbarHost &&
        createPortal(
          <>
            <ScannerWatchlistSelector
              lists={lists}
              selectedId={
                config.universe.source === "WATCHLIST"
                  ? config.universe.watchlist_id
                  : undefined
              }
              onSelect={(id) => {
                setOptionability(null);
                setConfig((current) => ({
                  ...current,
                  universe: {
                    source: "WATCHLIST",
                    watchlist_id: id,
                    symbols: [],
                  },
                }));
              }}
            />
            <button
              disabled
              title="Derivatives scan templates are not available"
            >
              Scan Templates ▾
            </button>
            <button onClick={() => setPanelView("saved")}>My Scans</button>
            <ScannerHistoryMenu
              onRecent={() => setPanelView("recent")}
              onHistory={() => setPanelView("history")}
            />
            <button onClick={() => setPanelView("movers")}>
              Market Movers
            </button>
            <button className="wl-primary" onClick={() => void save()}>
              ＋ Save Scan
            </button>
          </>,
          toolbarHost,
        )}
      <div
        className="wl-card sc-chips derivative-active-bar"
        aria-label="Active derivatives scan configuration"
      >
        {(config.universe.source === "WATCHLIST" ||
          parseSymbols(raw).length > 0) && (
          <button
            aria-label="Remove selected underlyings"
            onClick={() => {
              setConfig((c) => ({
                ...c,
                universe: { source: "CUSTOM", symbols: [] },
              }));
              setRaw("");
            }}
          >
            Underlyings:{" "}
            {(config.universe.source === "CUSTOM"
              ? parseSymbols(raw)
              : config.universe.source === "WATCHLIST"
                ? [
                    lists.find(
                      (list) => list.id === config.universe.watchlist_id,
                    )?.name || "Unavailable watchlist",
                  ]
                : config.universe.symbols
            ).join(", ") || "None selected"}{" "}
            {config.universe.source === "WATCHLIST" &&
            lists.find((list) => list.id === config.universe.watchlist_id)
              ?.read_only
              ? "🔒"
              : ""}{" "}
            ×
          </button>
        )}
        {config.expiry_mode === "EXACT" ? (
          <button
            aria-label="Remove exact expiry"
            onClick={() =>
              setConfig((c) => ({
                ...c,
                expiry_mode: "NEAREST",
                exact_expiry: null,
              }))
            }
          >
            Expiry: {config.exact_expiry || "Choose date"} ×
          </button>
        ) : (
          <span>Expiry: Nearest active</span>
        )}
        <span>±{config.strike_window} strikes</span>
        {optionType === "BOTH" ? (
          <span>Option Type: Both</span>
        ) : (
          <button
            aria-label={`Reset Option Type ${optionType} to Both`}
            onClick={() => selectOptionType("BOTH")}
          >
            Option Type: {optionType} ×
          </button>
        )}
        {config.filters
          .filter((f) => f.field !== "option_type")
          .map((f) => (
            <button
              key={f.field}
              className="derivative-predicate-chip"
              aria-label={`Remove ${filterText(f, catalog?.fields || [])} filter`}
              onClick={() =>
                setConfig((c) => ({
                  ...c,
                  filters: c.filters.filter((item) => item.field !== f.field),
                }))
              }
            >
              {filterText(f, catalog?.fields || [])} ×
            </button>
          ))}
        {config.filters.length > 0 && (
          <button
            className="derivative-clear-all"
            onClick={() => setConfig((c) => ({ ...c, filters: [] }))}
          >
            Clear All
          </button>
        )}
      </div>
      <div
        className={`sc-grid conditional-detail-layout${panelView ? " has-detail" : ""}`}
      >
        <aside className="wl-card sc-builder derivative-builder">
          <h2>Build an options scan</h2>
          <p>
            Select up to 5 optionable underlyings, choose expiry and add
            explicit filters.
          </p>
          {config.universe.source === "WATCHLIST" ? (
            <div className="sc-universe-summary">
              <strong>
                {lists.find((list) => list.id === config.universe.watchlist_id)
                  ?.name || "Selected watchlist unavailable"}
              </strong>
              {lists.find((list) => list.id === config.universe.watchlist_id)
                ?.read_only && <span> 🔒 Built-in · read-only</span>}
              {optionability ? (
                <small>
                  {optionability.members} watchlist members ·{" "}
                  {optionability.optionable} optionable ·{" "}
                  {config.universe.symbols.length} selected (maximum 5).
                  Non-optionable members are not scanned.
                </small>
              ) : (
                <small>
                  Checking optionability against the active O2 instrument
                  master…
                </small>
              )}
              {optionability && (
                <details>
                  <summary>Choose optionable underlyings</summary>
                  <div className="sc-members">
                    {optionability.symbols.map((symbol) => (
                      <label key={symbol}>
                        <input
                          type="checkbox"
                          checked={config.universe.symbols.includes(symbol)}
                          onChange={(event) => {
                            const current = config.universe.symbols;
                            if (event.target.checked && current.length >= 5) {
                              setError("Select no more than 5 underlyings.");
                              return;
                            }
                            if (!event.target.checked && current.length === 1) {
                              setError(
                                "Keep at least one underlying selected.",
                              );
                              return;
                            }
                            setConfig((configuration) => ({
                              ...configuration,
                              universe: {
                                ...configuration.universe,
                                symbols: event.target.checked
                                  ? [...current, symbol]
                                  : current.filter((item) => item !== symbol),
                              },
                            }));
                          }}
                        />
                        {symbol}
                      </label>
                    ))}
                  </div>
                </details>
              )}
            </div>
          ) : customOpen || raw ? (
            <label className="sc-label">
              NSE underlyings
              <textarea
                rows={3}
                value={raw}
                onChange={(event) => setRaw(event.target.value)}
                placeholder="NIFTY, BANKNIFTY, RELIANCE"
              />
            </label>
          ) : null}
          <button
            type="button"
            className="sc-custom-action"
            onClick={() => {
              setConfig((current) => ({
                ...current,
                universe: { source: "CUSTOM", symbols: [] },
              }));
              setCustomOpen(true);
              setOptionability(null);
            }}
          >
            Custom underlyings
          </button>
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
          <fieldset className="derivative-option-type">
            <legend>Option Type</legend>
            {(["CE", "PE", "BOTH"] as const).map((side) => (
              <label key={side}>
                <input
                  type="radio"
                  name="derivative-option-type"
                  value={side}
                  checked={optionType === side}
                  onChange={() => selectOptionType(side)}
                />
                <span>{side === "BOTH" ? "Both" : side}</span>
              </label>
            ))}
          </fieldset>
          <details className="derivative-filter-editor">
            <summary>＋ Add Filter</summary>
            <h3>Additional Filters</h3>
            <h4>Add / edit filter</h4>
            {catalogError && (
              <div className="wl-error" role="alert">
                {catalogError}{" "}
                <button
                  onClick={() => setCatalogRetry((attempt) => attempt + 1)}
                >
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
                          .filter(
                            (f) =>
                              f.category === category &&
                              f.field !== "option_type",
                          )
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
                <select
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                >
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
                "oi_percentile",
                "oi_vs_chain_median",
                "oi_change_percentile",
              ].includes(spec.field) && (
                <small>
                  Relative volume and OI use CE and PE contracts from this
                  underlying and expiry&apos;s bounded chain. ΔOI percentile
                  ranks absolute change magnitude; direction remains in ΔOI and
                  ΔOI %. Missing observations cannot pass an active filter.
                </small>
              )}
            {spec?.provider_dependent && (
              <small>
                This field can be unavailable in the current Dhan chain; an
                active filter cannot pass missing data.
              </small>
            )}
            <button onClick={addFilter} disabled={!spec}>
              Add / update filter
            </button>
          </details>
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
                setChecked([]);
                setPanelView(null);
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
                    : "Ready to scan"}
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
                  <ScannerColumnsMenu
                    options={resultColumnOptions}
                    selected={visibleColumns}
                    onChange={(key, checked) =>
                      setVisibleColumns((current) =>
                        checked
                          ? [...current, key as ResultColumn]
                          : current.filter((column) => column !== key),
                      )
                    }
                  />
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
                        ["oi_percentile", "OI Pctl"],
                        ["oi_vs_chain_median", "OI vs Median"],
                        ["change_in_open_interest", "ΔOI"],
                        ["oi_change_percent", "ΔOI %"],
                        ["oi_change_percentile", "ΔOI Percentile"],
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
                        <th>Select</th>
                        {resultColumnOptions
                          .filter(([key]) => visibleColumns.includes(key))
                          .map(([key, label]) => (
                            <th key={key} title={resultColumnHelp[label]}>
                              {label}
                            </th>
                          ))}
                        <th>Actions</th>
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
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Select ${row.contract.display_symbol}`}
                              checked={checked.includes(
                                row.contract.canonical_id,
                              )}
                              onChange={(event) =>
                                setChecked((current) =>
                                  event.target.checked
                                    ? [...current, row.contract.canonical_id]
                                    : current.filter(
                                        (id) =>
                                          id !== row.contract.canonical_id,
                                      ),
                                )
                              }
                            />
                          </td>
                          {resultColumnOptions
                            .filter(([key]) => visibleColumns.includes(key))
                            .map(([key]) => (
                              <td key={key}>{resultCell(row, key)}</td>
                            ))}
                          <td>{rowActions(row)}</td>
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
                        <label>
                          <input
                            type="checkbox"
                            aria-label={`Select ${row.contract.display_symbol}`}
                            checked={checked.includes(
                              row.contract.canonical_id,
                            )}
                            onChange={(event) =>
                              setChecked((current) =>
                                event.target.checked
                                  ? [...current, row.contract.canonical_id]
                                  : current.filter(
                                      (id) => id !== row.contract.canonical_id,
                                    ),
                              )
                            }
                          />
                          <strong>
                            <Link
                              className="derivative-underlying-link"
                              href={underlyingHref(row)}
                              aria-label={`Open ${row.contract.underlying_symbol} in Options Analytics`}
                            >
                              {row.underlying}
                            </Link>{" "}
                            {num(row.strike)} {row.option_type}
                          </strong>
                        </label>
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
                      <p>
                        OI Pctl {num(row.oi_percentile)} · ΔOI{" "}
                        {signed(row.market.change_in_open_interest)} · ΔOI %{" "}
                        {signed(row.oi_change_percent, "%")}
                      </p>
                      <OiBadge row={row} />
                      <p>{row.reason}</p>
                      {rowActions(row)}
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
              <div className="sc-empty">
                <h2>Ready to scan</h2>
                <p>
                  Select an underlying watchlist or enter Custom underlyings,
                  choose expiry and option settings, add a filter, then Run
                  Scan.
                </p>
              </div>
            )}
          </section>
          <div
            className="wl-card sc-bulk derivative-bulk"
            aria-label="Derivatives selection actions"
          >
            <span>{checked.length} selected</span>
            <button
              disabled
              title="Option-contract watchlist mapping is unavailable"
            >
              ＋ Add Selected to Watchlist
            </button>
            <button disabled title="Derivatives CSV export is unavailable">
              Export CSV
            </button>
            {checked.length === 1 && selectedForAction ? (
              <Link href={analyticsHref(selectedForAction)}>
                Open in Options Analytics
              </Link>
            ) : (
              <button disabled>Open in Options Analytics</button>
            )}
            <button disabled title="Exact option charts are unavailable">
              Open in Chart
            </button>
            <button disabled title="Derivatives comparison is unavailable">
              Compare
            </button>
          </div>
        </main>
        {panelView && (
          <aside
            className="wl-card derivative-detail sc-context-panel"
            aria-label={
              panelView === "detail"
                ? "Selected option contract"
                : "Scanner contextual panel"
            }
          >
            <header className="sc-context-head">
              <h2>
                {panelView === "detail"
                  ? "Instrument Analysis"
                  : panelView === "saved"
                    ? "My Scans"
                    : panelView === "history"
                      ? "Scan History"
                      : panelView === "movers"
                        ? "Market Movers"
                        : "Recent Scans"}
              </h2>
              <button
                className="detail-panel-clear"
                aria-label="Close panel"
                onClick={() => setPanelView(null)}
              >
                ×
              </button>
            </header>
            {panelView === "saved" && (
              <div className="sc-utility-list">
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
              </div>
            )}
            {(panelView === "recent" || panelView === "history") && (
              <div className="sc-utility-list">
                <h3>
                  {panelView === "history" ? "Scan History" : "Recent Scans"}
                </h3>
                {history
                  .slice(0, panelView === "history" ? 50 : 10)
                  .map((h) => (
                    <div key={h.id} className="derivative-history-item">
                      <span>
                        {h.config.name} · {h.counts.matches} matches ·{" "}
                        {new Date(h.created_at).toLocaleString("en-IN")}
                      </span>
                      <button onClick={() => void view(h.id)}>View</button>
                    </div>
                  ))}
                {!history.length && <p>No derivatives scan history yet.</p>}
              </div>
            )}
            {panelView === "movers" && (
              <div className="sc-utility-list sc-movers">
                <p>
                  TapTide · Optional provider-wide evidence. Load on demand.
                </p>
                <button
                  disabled={moversBusy}
                  onClick={() =>
                    void (async () => {
                      setMoversBusy(true);
                      try {
                        setMovers(await scannerApi<ProviderResults>("movers"));
                        setError("");
                      } catch (error) {
                        setError((error as Error).message);
                      } finally {
                        setMoversBusy(false);
                      }
                    })()
                  }
                >
                  Load movers
                </button>
                <button
                  disabled={moversBusy}
                  onClick={() =>
                    void (async () => {
                      setMoversBusy(true);
                      try {
                        setMovers(
                          await scannerApi<ProviderResults>(
                            "provider-screen",
                            "POST",
                            {
                              ...initialConfig,
                              universe: {
                                source: "CUSTOM",
                                symbols: ["NIFTY"],
                                instrument_ids: [],
                              },
                            },
                          ),
                        );
                        setError("");
                      } catch (error) {
                        setError((error as Error).message);
                      } finally {
                        setMoversBusy(false);
                      }
                    })()
                  }
                >
                  TapTide technical screen
                </button>
                <div className="sc-periods">
                  {[
                    "Top Gainers",
                    "Top Losers",
                    "High Volume",
                    "52W High",
                    "52W Low",
                  ].map((tab) => (
                    <button
                      key={tab}
                      aria-pressed={moverTab === tab}
                      onClick={() => setMoverTab(tab)}
                    >
                      {tab}
                    </button>
                  ))}
                </div>
                {movers && (
                  <>
                    <small>
                      {movers.tool === "screen_stocks_technical"
                        ? "Technical screen results · "
                        : ""}
                      {movers.state} · {movers.coverage} · {movers.freshness}
                    </small>
                    {[...movers.rows]
                      .filter((row) =>
                        movers.tool === "screen_stocks_technical"
                          ? true
                          : moverTab === "52W High"
                            ? (row.buckets || [row.bucket]).includes(
                                "near_52w_high",
                              )
                            : moverTab === "52W Low"
                              ? (row.buckets || [row.bucket]).includes(
                                  "near_52w_low",
                                )
                              : moverTab === "Top Gainers"
                                ? Number(row.metrics.change) > 0
                                : moverTab === "Top Losers"
                                  ? Number(row.metrics.change) < 0
                                  : true,
                      )
                      .sort((a, b) =>
                        moverTab === "High Volume"
                          ? Number(b.metrics.volume) - Number(a.metrics.volume)
                          : moverTab === "Top Losers"
                            ? Number(a.metrics.change) -
                              Number(b.metrics.change)
                            : Number(b.metrics.change) -
                              Number(a.metrics.change),
                      )
                      .slice(0, 5)
                      .map((row) => (
                        <article key={row.symbol}>
                          <button
                            onClick={() => {
                              setConfig((current) => ({
                                ...current,
                                universe: { source: "CUSTOM", symbols: [] },
                              }));
                              setRaw(row.symbol);
                              setNotice(
                                "Symbol loaded. Review optionability and run the Dhan scan to evaluate your filters.",
                              );
                            }}
                          >
                            {row.symbol}
                          </button>
                          <span
                            className={
                              Number(row.metrics.change) > 0 ? "up" : "down"
                            }
                          >
                            {changeText(row.metrics.change)}
                          </span>
                        </article>
                      ))}
                  </>
                )}
              </div>
            )}
            {panelView === "detail" && selected && (
              <div>
                <button
                  className="detail-panel-clear"
                  onClick={() => {
                    setSelected(null);
                    setPanelView(null);
                  }}
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
                    LTP {num(selected.market.ltp)} · Bid{" "}
                    {num(selected.market.bid)} · Ask {num(selected.market.ask)}
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
                    {signed(selected.market.change_in_open_interest)} · ΔOI %{" "}
                    {signed(selected.oi_change_percent, "%")}
                  </dd>
                  <dt>Relative OI context</dt>
                  <dd>
                    OI percentile {num(selected.oi_percentile)} · chain median{" "}
                    {num(selected.oi_chain_median)} · vs median{" "}
                    {selected.oi_vs_chain_median == null
                      ? "—"
                      : `${num(selected.oi_vs_chain_median)}x`}{" "}
                    · absolute ΔOI percentile{" "}
                    {num(selected.oi_change_percentile)}
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
                  <p>
                    Missing evidence: {selected.missing_evidence.join(", ")}
                  </p>
                )}
                {selected.warnings.length > 0 && (
                  <p>Warnings: {selected.warnings.join(", ")}</p>
                )}
                <section
                  className="derivative-oi-evidence"
                  aria-label="OI interpretation evidence"
                >
                  <h3>OI Interpretation (Inferred)</h3>
                  <OiBadge row={selected} />
                  <p>
                    Evidence quality:{" "}
                    {selected.oi_interpretation?.confidence || "INSUFFICIENT"}
                  </p>
                  <dl>
                    <dt>Premium change</dt>
                    <dd>
                      {signed(
                        selected.oi_interpretation?.premium_change_percent,
                        "%",
                      )}
                    </dd>
                    <dt>OI change over comparison window</dt>
                    <dd>
                      {signed(
                        selected.oi_interpretation?.oi_window_change_percent,
                        "%",
                      )}
                    </dd>
                    <dt>Underlying change</dt>
                    <dd>
                      {signed(
                        selected.oi_interpretation?.underlying_change_percent,
                        "%",
                      )}
                    </dd>
                    <dt>IV change</dt>
                    <dd>
                      {signed(
                        selected.oi_interpretation?.iv_change_points,
                        " pp",
                      )}
                    </dd>
                    <dt>Window</dt>
                    <dd>
                      {selected.oi_interpretation?.window_start ||
                        "Unavailable"}{" "}
                      to{" "}
                      {selected.oi_interpretation?.window_end || "Unavailable"}
                      {" · "}
                      {selected.oi_interpretation?.window_seconds == null
                        ? "duration unavailable"
                        : `${num(selected.oi_interpretation.window_seconds)} seconds`}
                    </dd>
                    <dt>Freshness</dt>
                    <dd>
                      {selected.oi_interpretation?.freshness || "INSUFFICIENT"}
                    </dd>
                  </dl>
                  <small>
                    {selected.oi_interpretation?.reason ||
                      "Historical interpretation unavailable"}
                  </small>
                </section>
                <h3>Provenance</h3>
                <p>
                  Dhan · {selected.provenance.market_source} ·{" "}
                  {selected.provenance.freshness}
                  {selected.provenance.cached ? " · cached" : " · retrieved"}
                </p>
                <small>
                  Source time:{" "}
                  {selected.provenance.source_time || "Unavailable"}
                  <br />
                  Retrieved: {selected.provenance.received_at}
                </small>
                <div className="derivative-detail-actions">
                  <Link href={analyticsHref(selected)}>
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
                    className="wl-buy"
                    disabled={!broker || expiredContract(selected.contract)}
                    onClick={() => openTrade(selected, "BUY")}
                  >
                    Buy · Broker V2 preview
                  </button>
                  <button
                    className="wl-sell"
                    disabled={!broker || expiredContract(selected.contract)}
                    onClick={() => openTrade(selected, "SELL")}
                  >
                    Sell · Broker V2 preview
                  </button>
                </div>
                <small>
                  Broker preview requires separate confirmation. Expired
                  historical contracts cannot be traded.
                </small>
              </div>
            )}
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
