"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { OrderTicket } from "../brokers/order-ticket";
import { Icon } from "../shell/icon";
import { brokerApi, type Account, type Instrument } from "../../lib/brokers";
import type { Capability, Choices, Side } from "../../lib/broker-orders";
import { scannerApi, type ProviderResults } from "../../lib/scanner";
import { watchApi, type Watchlist } from "../../lib/watchlists";
import { ScannerWatchlistSelector } from "./watchlist-selector";
import {
  DerivativeTemplateMenu,
  type DerivativeTemplate,
} from "./derivative-template-menu";
import { DerivativeSaveMenu } from "./derivative-save-menu";
import { ScannerHistoryMenu } from "./scanner-history-menu";
import { ScannerColumnsMenu } from "./scanner-columns-menu";

type Field = {
  field: string;
  category: string;
  label: string;
  kind: "enum" | "number" | "integer";
  values?: string[];
  operators: string[];
  minimum?: number;
  maximum?: number;
  unit?: string;
};
type Filter = {
  field: string;
  operator: string;
  value: string | number | number[] | string[];
};
type Config = {
  name: string;
  scanner_type: "DERIVATIVES";
  instrument_scope: "FUTURES";
  data_mode: "REAL";
  provider: "dhan";
  universe: {
    source: "CUSTOM" | "WATCHLIST";
    symbols: string[];
    watchlist_id?: string;
  };
  expiry_mode: "NEAREST" | "EXACT";
  exact_expiry: string | null;
  filters: Filter[];
  version: "1";
  origin_template_id?: string | null;
  origin_template_name?: string | null;
};
type Row = {
  contract: {
    canonical_id: string;
    exchange: string;
    underlying_symbol: string;
    instrument_type: "FUTSTK" | "FUTIDX";
    expiry: string;
    trading_symbol: string;
    provider_native_id: string;
    lot_size: number | null;
    tick_size: string | null;
  };
  underlying: string;
  expiry: string;
  dte: number;
  quote: {
    last_price: string;
    open: string | null;
    volume: string | null;
    open_interest: string | null;
    provider_source_time: string | null;
    received_at: string;
  } | null;
  spot_quote: {
    last_price: string;
    provider_source_time: string | null;
  } | null;
  observed: Record<string, string | number | null>;
  volume_percentile: number | null;
  relative_volume_cohort_size: number;
  oi_percentile: number | null;
  relative_oi_cohort_size: number;
  basis_reason: string;
  spot_change_percent: number | null;
  comparison_window: { from: string; to: string; seconds: number } | null;
  futures_interpretation: { label: string; inferred: boolean; reason: string };
  source_time: string | null;
  received_at: string | null;
  outcome: "MATCH" | "NON_MATCH" | "NOT_EVALUATED";
  diagnostics: {
    filter: Filter;
    observed: string | number | null;
    threshold: unknown;
    passed: boolean | null;
    reason: string;
  }[];
  missing_evidence: string[];
  reason: string;
  evaluation_reason?: { code: string; detail: string } | null;
  evaluation_reasons?: { code: string; detail: string }[];
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
    contract_id?: string;
    evaluation_reason?: { code: string; detail: string } | null;
    evidence_status?: Record<string, string>;
  }[];
  not_evaluated_reasons?: Record<string, number>;
  performance?: Record<string, number>;
};
type Saved = {
  id: string;
  config: Config;
  archived: boolean;
  updated_at: string;
};
const initial: Config = {
  name: "Futures scan",
  scanner_type: "DERIVATIVES",
  instrument_scope: "FUTURES",
  data_mode: "REAL",
  provider: "dhan",
  universe: { source: "CUSTOM", symbols: [] },
  expiry_mode: "NEAREST",
  exact_expiry: null,
  filters: [],
  version: "1",
};
const columns = [
  ["underlying", "Symbol"],
  ["expiry", "Expiry"],
  ["ltp", "Fut Price"],
  ["open", "Open Price"],
  ["change_percent", "Change %"],
  ["volume", "Volume"],
  ["volume_percentile", "Vol Pctl"],
  ["open_interest", "OI"],
  ["oi_percentile", "OI Pctl"],
  ["change_in_open_interest", "ΔOI"],
  ["oi_change_percent", "ΔOI %"],
  ["basis_abs", "Basis (Abs)"],
  ["basis_percent", "Basis %"],
  ["underlying_trend", "Spot Direction"],
  ["interpretation", "Futures Interpretation"],
] as const;
type Column = (typeof columns)[number][0];
const defColumns: Column[] = columns.map(([key]) => key);
const numeric = (value: string | number | null | undefined, decimals = 2) =>
  value == null || !Number.isFinite(Number(value))
    ? "—"
    : Number(value).toLocaleString("en-IN", {
        maximumFractionDigits: decimals,
      });
const signed = (value: string | number | null | undefined, suffix = "") =>
  value == null || !Number.isFinite(Number(value))
    ? "—"
    : `${Number(value) > 0 ? "+" : ""}${numeric(value)}${suffix}`;
const symbolsFrom = (raw: string) => [
  ...new Set(
    raw
      .split(/[\s,]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean),
  ),
];
const filterLabel = (item: Filter, catalog: Field[]) =>
  `${catalog.find((f) => f.field === item.field)?.label || item.field} ${item.operator} ${Array.isArray(item.value) ? item.value.join(" – ") : item.value}`;

function todayInIndia(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

export function FuturesScanner({ active }: { active: boolean }) {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [catalog, setCatalog] = useState<{
    fields: Field[];
    max_underlyings: number;
  } | null>(null);
  const [catalogStatus, setCatalogStatus] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [lists, setLists] = useState<Watchlist[]>([]);
  const [listsStatus, setListsStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [templates, setTemplates] = useState<{
    built_in: DerivativeTemplate[];
    user: DerivativeTemplate[];
  }>({ built_in: [], user: [] });
  const [templatesStatus, setTemplatesStatus] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [config, setConfig] = useState<Config>(initial);
  const [raw, setRaw] = useState("");
  const [eligible, setEligible] = useState<{
    members: number;
    eligible: number;
    excluded: string[];
    symbols: string[];
  } | null>(null);
  const [eligibilityStatus, setEligibilityStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [field, setField] = useState("");
  const [operator, setOperator] = useState(">=");
  const [value, setValue] = useState("");
  const [upper, setUpper] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [selected, setSelected] = useState<Row | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [panel, setPanel] = useState<
    "detail" | "saved" | "recent" | "history" | "movers" | null
  >(null);
  const [showAll, setShowAll] = useState(false);
  const [movers, setMovers] = useState<ProviderResults | null>(null);
  const [moversBusy, setMoversBusy] = useState(false);
  const [moverTab, setMoverTab] = useState("Top Gainers");
  const [sort, setSort] = useState("canonical");
  const [visible, setVisible] = useState<Column[]>(defColumns);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [broker, setBroker] = useState<{
    account: Account;
    capability: Capability;
  } | null>(null);
  const [ticket, setTicket] = useState<{
    account: Account;
    instrument: Instrument;
    side: Side;
  } | null>(null);
  const spec = catalog?.fields.find((item) => item.field === field);
  const selectedList = lists.find(
    (item) => item.id === config.universe.watchlist_id,
  );
  const visibleRows = (run?.rows || [])
    .filter((item) => showAll || item.outcome === "MATCH")
    .sort((a, b) => {
      if (sort === "canonical") return 0;
      const av = a.observed[sort],
        bv = b.observed[sort];
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av ?? "").localeCompare(String(bv ?? ""));
    });
  useEffect(() => {
    const frame = requestAnimationFrame(() =>
      setHost(document.getElementById("sc-derivative-toolbar")),
    );
    return () => cancelAnimationFrame(frame);
  }, []);
  useEffect(() => {
    void scannerApi<{ fields: Field[]; max_underlyings: number }>(
      "derivatives/futures/catalog",
    )
      .then((items) => {
        setCatalog(items);
        setCatalogStatus("ready");
      })
      .catch((reason: Error) => {
        setCatalogStatus("error");
        setError(`Futures filter catalog unavailable: ${reason.message}`);
      });
    void watchApi<Watchlist[]>("")
      .then((items) => {
        if (!Array.isArray(items)) throw new Error("Invalid watchlist catalog");
        setLists(items.filter((item) => !item.archived));
        setListsStatus("ready");
      })
      .catch(() => setListsStatus("error"));
    void scannerApi<{
      built_in: DerivativeTemplate[];
      user: DerivativeTemplate[];
    }>("derivatives/templates")
      .then((items) => {
        if (!Array.isArray(items.built_in) || !Array.isArray(items.user))
          throw new Error("Invalid template catalog");
        setTemplates(items);
        setTemplatesStatus("ready");
      })
      .catch(() => setTemplatesStatus("error"));
    void scannerApi<Run[]>("derivatives/runs")
      .then((items) =>
        setHistory(
          items.filter((item) => item.config.instrument_scope === "FUTURES"),
        ),
      )
      .catch(() => setError("Recent Futures scans could not be loaded."));
    void scannerApi<Saved[]>("derivatives/saved")
      .then((items) =>
        setSaved(
          items.filter((item) => item.config.instrument_scope === "FUTURES"),
        ),
      )
      .catch(() => setError("Saved Futures scans could not be loaded."));
    void brokerApi<Account[]>("accounts")
      .then(async (accounts) => {
        const connected = accounts.filter((a) => a.state === "connected");
        const capabilities = await Promise.all(
          connected.map(async (account) => {
            try {
              const capability = await brokerApi<Capability>(
                `accounts/${account.id}/order-entry/capabilities`,
              );
              return capability.enabled && capability.broker.supports_futures
                ? { account, capability }
                : null;
            } catch {
              return null;
            }
          }),
        );
        const first = capabilities.find((x) => x !== null);
        if (first) setBroker(first);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (config.universe.source !== "WATCHLIST" || !config.universe.watchlist_id)
      return;
    let live = true;
    const id = config.universe.watchlist_id;
    void scannerApi<{
      members: number;
      eligible: number;
      excluded: string[];
      symbols: string[];
    }>(`derivatives/futures/watchlists/${id}/eligible`)
      .then((result) => {
        if (!live) return;
        setEligible(result);
        setEligibilityStatus("ready");
        setConfig((current) =>
          current.universe.source === "WATCHLIST" &&
          current.universe.watchlist_id === id &&
          !current.universe.symbols.length
            ? {
                ...current,
                universe: {
                  ...current.universe,
                  symbols: result.symbols.length <= 50 ? result.symbols : [],
                },
              }
            : current,
        );
      })
      .catch((e: Error) => {
        if (live) {
          setEligible(null);
          setEligibilityStatus("error");
          setError(`Watchlist futures eligibility unavailable: ${e.message}`);
        }
      });
    return () => {
      live = false;
    };
  }, [config.universe.source, config.universe.watchlist_id]);
  function editField(next: string) {
    const item = catalog?.fields.find((x) => x.field === next);
    setField(next);
    setOperator(item?.kind === "enum" ? "equals" : ">=");
    setValue(item?.values?.[0] || "");
    setUpper("");
  }
  function addFilter() {
    if (!spec) return;
    let next: Filter;
    if (spec.kind === "enum") next = { field, operator, value };
    else {
      const n = Number(value),
        u = Number(upper);
      if (
        !value.trim() ||
        !Number.isFinite(n) ||
        (operator === "between" &&
          (!upper.trim() || !Number.isFinite(u) || u < n)) ||
        (spec.kind === "integer" &&
          (!Number.isInteger(n) ||
            (operator === "between" && !Number.isInteger(u)))) ||
        (spec.minimum != null && n < spec.minimum) ||
        (spec.maximum != null && n > spec.maximum)
      ) {
        setError("Enter a valid value within the field bounds.");
        return;
      }
      next = { field, operator, value: operator === "between" ? [n, u] : n };
    }
    setConfig((c) => ({
      ...c,
      filters: [...c.filters.filter((f) => f.field !== field), next],
    }));
    setError("");
  }
  function effectiveConfig(): Config | null {
    if (config.universe.source === "WATCHLIST") {
      if (!config.universe.watchlist_id) {
        setError("Choose a watchlist from the toolbar above.");
        return null;
      }
      if (selectedList?.enabled === false) {
        setError("This built-in watchlist is not ready for scanning.");
        return null;
      }
      if (eligibilityStatus !== "ready") {
        setError(
          eligibilityStatus === "error"
            ? "Watchlist futures eligibility unavailable. Please retry later."
            : "Checking watchlist futures eligibility. Please wait.",
        );
        return null;
      }
    }
    const symbols =
      config.universe.source === "CUSTOM"
        ? symbolsFrom(raw)
        : config.universe.symbols;
    if (!symbols.length || symbols.length > 50) {
      setError(
        config.universe.source === "CUSTOM"
          ? symbols.length > 50
            ? "Select no more than 50 custom NSE underlyings. Nothing was truncated."
            : "Enter custom underlyings or choose a watchlist."
          : symbols.length > 50
            ? "Choose up to 50 futures-eligible watchlist members. Nothing was truncated."
            : "No futures-eligible underlyings are selected from this watchlist.",
      );
      return null;
    }
    if (!config.filters.length) {
      setError("Add at least one explicit filter before scanning.");
      return null;
    }
    if (config.expiry_mode === "EXACT" && !config.exact_expiry) {
      setError("Choose the exact expiry.");
      return null;
    }
    return { ...config, universe: { ...config.universe, symbols } };
  }
  async function execute() {
    const submitted = effectiveConfig();
    if (!submitted) return;
    setBusy(true);
    setError("");
    setSelected(null);
    setPanel(null);
    setChecked([]);
    try {
      const next = await scannerApi<Run>(
        "derivatives/futures/runs",
        "POST",
        submitted,
      );
      setRun(next);
      setHistory((h) => [next, ...h]);
      setNotice(`Futures scan complete: ${next.counts.matches} matches.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function saveScan() {
    const current = effectiveConfig();
    if (!current) return;
    const name = window.prompt("Saved futures scan name", current.name)?.trim();
    if (!name) return;
    try {
      const next = await scannerApi<Saved>(
        "derivatives/futures/saved",
        "POST",
        { config: { ...current, name }, archived: false },
      );
      setSaved((s) => [next, ...s]);
      setNotice("Futures scan saved.");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function saveTemplate() {
    if (!config.filters.length) {
      setError("Add a filter before saving a template.");
      return;
    }
    const name = window.prompt("Futures template name")?.trim();
    if (!name) return;
    const choice = window
      .prompt("Horizon: INTRADAY, POSITIONAL or GENERAL", "GENERAL")
      ?.trim()
      .toUpperCase();
    if (!choice || !["INTRADAY", "POSITIONAL", "GENERAL"].includes(choice)) {
      setError("Choose INTRADAY, POSITIONAL or GENERAL.");
      return;
    }
    try {
      const next = await scannerApi<DerivativeTemplate>(
        "derivatives/templates",
        "POST",
        {
          template_schema_version: 1,
          name,
          horizon: choice,
          description: "Custom Futures setup",
          recipe: {
            scanner_type: "DERIVATIVES",
            instrument_scope: "FUTURES",
            expiry_mode: config.expiry_mode,
            exact_expiry: config.exact_expiry,
            strike_window: 10,
            watchlist_id:
              config.universe.source === "WATCHLIST"
                ? config.universe.watchlist_id
                : null,
            predicates: config.filters,
          },
        },
      );
      setTemplates((t) => ({ ...t, user: [next, ...t.user] }));
      setNotice("Futures template saved. It contains configuration only.");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function renameTemplate(template: DerivativeTemplate) {
    if (template.source !== "USER") return;
    const name = window.prompt("Template name", template.name)?.trim();
    if (!name) return;
    try {
      const updated = await scannerApi<DerivativeTemplate>(
        `derivatives/templates/${template.template_id}`,
        "PATCH",
        {
          template_schema_version: 1,
          name,
          horizon: template.horizon,
          description: template.description,
          recipe: template.recipe,
        },
      );
      setTemplates((current) => ({
        ...current,
        user: current.user.map((item) =>
          item.template_id === updated.template_id ? updated : item,
        ),
      }));
      setNotice("Futures template renamed.");
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  async function deleteTemplate(template: DerivativeTemplate) {
    if (
      template.source !== "USER" ||
      !window.confirm(`Delete ${template.name}?`)
    )
      return;
    try {
      await scannerApi(
        `derivatives/templates/${template.template_id}`,
        "DELETE",
      );
      setTemplates((current) => ({
        ...current,
        user: current.user.filter(
          (item) => item.template_id !== template.template_id,
        ),
      }));
      setNotice("Futures template deleted.");
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  function loadTemplate(template: DerivativeTemplate) {
    if (
      template.instrument_scope !== "FUTURES" ||
      template.recipe.instrument_scope !== "FUTURES"
    ) {
      setError("Choose a Futures template.");
      return;
    }
    const fields = new Set(catalog?.fields.map((x) => x.field));
    if (
      !catalog ||
      template.recipe.predicates.some((f) => !fields.has(f.field))
    ) {
      setError("Template contains an unavailable Futures field.");
      return;
    }
    if (
      template.recipe.watchlist_id &&
      (config.universe.source !== "WATCHLIST" ||
        config.universe.watchlist_id !== template.recipe.watchlist_id)
    ) {
      setEligible(null);
      setEligibilityStatus("loading");
    }
    setConfig((c) => ({
      ...c,
      name: template.name,
      expiry_mode: template.recipe.expiry_mode,
      exact_expiry: template.recipe.exact_expiry,
      filters: template.recipe.predicates.map((f) => ({ ...f })),
      universe: template.recipe.watchlist_id
        ? {
            source: "WATCHLIST",
            watchlist_id: template.recipe.watchlist_id,
            symbols:
              c.universe.source === "WATCHLIST" &&
              c.universe.watchlist_id === template.recipe.watchlist_id
                ? c.universe.symbols
                : [],
          }
        : c.universe,
      origin_template_id: template.template_id,
      origin_template_name: template.name,
    }));
    setRun(null);
    setSelected(null);
    setChecked([]);
    setNotice(
      `${template.name} loaded. Review visible filters before running.`,
    );
  }
  function load(savedConfig: Config) {
    if (
      savedConfig.universe.source !== "WATCHLIST" ||
      config.universe.source !== "WATCHLIST" ||
      savedConfig.universe.watchlist_id !== config.universe.watchlist_id
    ) {
      setEligible(null);
      setEligibilityStatus(
        savedConfig.universe.source === "WATCHLIST" ? "loading" : "idle",
      );
    }
    setConfig(savedConfig);
    setRaw(
      savedConfig.universe.source === "CUSTOM"
        ? savedConfig.universe.symbols.join(", ")
        : "",
    );
    setRun(null);
    setSelected(null);
    setChecked([]);
    setPanel(null);
  }
  async function view(id: string) {
    try {
      const next = await scannerApi<Run>(`derivatives/runs/${id}`);
      if (next.config.instrument_scope !== "FUTURES")
        throw new Error("This is not a Futures scan.");
      setRun(next);
      setSelected(null);
      setChecked([]);
      setPanel(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function trade(row: Row, side: Side) {
    if (!broker) return;
    if (row.expiry < todayInIndia()) {
      setError("This futures contract has expired.");
      return;
    }
    if (!row.contract.lot_size || !row.contract.tick_size) {
      setError(
        "Dhan contract lot/tick metadata is unavailable; Broker handoff is disabled.",
      );
      return;
    }
    try {
      const query = new URLSearchParams({
        asset: "futures",
        underlying: row.underlying,
        expiry: row.expiry,
      });
      const choices = await brokerApi<Choices>(
        `accounts/${broker.account.id}/order-entry/choices?${query}`,
      );
      const exact = choices.instruments.filter(
        (item) =>
          item.exchange === "NFO" &&
          item.segment === "NFO-FUT" &&
          item.kind === "FUT" &&
          item.underlying === row.underlying &&
          item.expiry === row.expiry &&
          Number(item.lot_size) === row.contract.lot_size &&
          Number(item.tick_size) === Number(row.contract.tick_size),
      );
      if (exact.length !== 1)
        throw new Error(
          "An exact, unique broker futures contract was not found. Open Broker V2 to review it manually.",
        );
      setTicket({ account: broker.account, instrument: exact[0], side });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function exportCsv() {
    if (!run) return;
    const selectedRows = run.rows.filter((r) =>
      checked.includes(r.contract.canonical_id),
    );
    const lines = [
      "symbol,expiry,price,volume,oi,outcome",
      ...selectedRows.map((r) =>
        [
          r.underlying,
          r.expiry,
          r.observed.ltp ?? "",
          r.observed.volume ?? "",
          r.observed.open_interest ?? "",
          r.outcome,
        ].join(","),
      ),
    ];
    const url = URL.createObjectURL(
      new Blob([lines.join("\n")], { type: "text/csv" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `twf-futures-${run.id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
  function cell(row: Row, key: Column) {
    if (key === "underlying")
      return (
        <button
          className="derivative-underlying-link"
          onClick={() => {
            setSelected(row);
            setPanel("detail");
          }}
        >
          {row.underlying}
        </button>
      );
    if (key === "expiry") return row.expiry;
    if (key === "open") return numeric(row.quote?.open);
    if (key === "underlying_trend") {
      const trend = row.observed.underlying_trend;
      return (
        <span
          className={`derivative-trend derivative-trend-${trend === "Up" ? "up" : trend === "Down" ? "down" : "neutral"}`}
        >
          {trend === "Up" ? "▲ " : trend === "Down" ? "▼ " : ""}
          {trend || "—"}
        </span>
      );
    }
    if (key === "interpretation") {
      const label = row.futures_interpretation.label;
      const tone =
        label === "Long buildup"
          ? "call-long"
          : label === "Short buildup"
            ? "put-short"
            : "neutral";
      return (
        <span
          className={`derivative-oi-badge derivative-oi-${tone}`}
          title={`${row.futures_interpretation.reason} · Inferred evidence`}
        >
          {label}
        </span>
      );
    }
    const value = row.observed[key];
    if (
      key === "change_percent" ||
      key === "oi_change_percent" ||
      key === "basis_percent"
    )
      return (
        <span
          className={
            Number(value) > 0
              ? "derivative-positive"
              : Number(value) < 0
                ? "derivative-negative"
                : ""
          }
        >
          {signed(value, "%")}
        </span>
      );
    if (key === "change_in_open_interest" || key === "basis_abs")
      return (
        <span
          className={
            Number(value) > 0
              ? "derivative-positive"
              : Number(value) < 0
                ? "derivative-negative"
                : ""
          }
        >
          {signed(value)}
        </span>
      );
    if (key === "volume_percentile" || key === "oi_percentile")
      return <span className="derivative-percentile">{numeric(value)}</span>;
    return numeric(value);
  }
  return (
    <div
      className="derivative-scanner futures-scanner"
      role="tabpanel"
      aria-label="Futures Scanner"
    >
      {error && (
        <div className="wl-error" role="alert">
          {error}{" "}
          <button onClick={() => setError("")} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}
      {notice && (
        <div className="wl-toast" role="status">
          {notice}{" "}
          <button onClick={() => setNotice("")} aria-label="Dismiss notice">
            ×
          </button>
        </div>
      )}
      {active &&
        host &&
        createPortal(
          <>
            <ScannerWatchlistSelector
              lists={lists}
              status={listsStatus}
              selectedId={
                config.universe.source === "WATCHLIST"
                  ? config.universe.watchlist_id
                  : undefined
              }
              onSelect={(id) => {
                setRun(null);
                setSelected(null);
                setChecked([]);
                setEligible(null);
                setEligibilityStatus("loading");
                setError("");
                setConfig((c) => ({
                  ...c,
                  universe: {
                    source: "WATCHLIST",
                    watchlist_id: id,
                    symbols: [],
                  },
                }));
              }}
            />
            <DerivativeTemplateMenu
              status={
                catalogStatus === "error" || templatesStatus === "error"
                  ? "error"
                  : catalogStatus === "ready" && templatesStatus === "ready"
                    ? "ready"
                    : "loading"
              }
              builtIn={templates.built_in.filter(
                (t) => t.instrument_scope === "FUTURES",
              )}
              user={templates.user.filter(
                (t) => t.instrument_scope === "FUTURES",
              )}
              onLoad={loadTemplate}
              onRename={(item) => void renameTemplate(item)}
              onDelete={(item) => void deleteTemplate(item)}
            />
            <button onClick={() => setPanel("saved")}>My Scans</button>
            <ScannerHistoryMenu
              onRecent={() => setPanel("recent")}
              onHistory={() => setPanel("history")}
            />
            <button onClick={() => setPanel("movers")}>Market Movers</button>
            <DerivativeSaveMenu
              onSaveScan={() => void saveScan()}
              onSaveTemplate={() => void saveTemplate()}
            />
          </>,
          host,
        )}
      <div
        className="wl-card sc-chips derivative-active-bar"
        aria-label="Active Futures scan configuration"
      >
        {(config.universe.source === "WATCHLIST" || raw.trim()) && (
          <button
            onClick={() => {
              setConfig((c) => ({
                ...c,
                universe: { source: "CUSTOM", symbols: [] },
              }));
              setRaw("");
            }}
          >
            {config.universe.source === "WATCHLIST"
              ? `Underlyings: ${selectedList?.name || "Watchlist"}`
              : `Underlyings: ${symbolsFrom(raw).join(", ")}`}{" "}
            ×
          </button>
        )}
        <button
          onClick={() =>
            setConfig((c) => ({
              ...c,
              expiry_mode: "NEAREST",
              exact_expiry: null,
            }))
          }
        >
          Expiry:{" "}
          {config.expiry_mode === "NEAREST"
            ? "Nearest active"
            : config.exact_expiry}{" "}
          ×
        </button>
        {config.origin_template_name && (
          <button
            onClick={() =>
              setConfig((c) => ({
                ...c,
                origin_template_id: null,
                origin_template_name: null,
              }))
            }
          >
            Template: {config.origin_template_name} ×
          </button>
        )}
        {config.filters.map((f) => (
          <button
            className="derivative-predicate-chip"
            key={f.field}
            onClick={() =>
              setConfig((c) => ({
                ...c,
                filters: c.filters.filter((x) => x.field !== f.field),
              }))
            }
          >
            {filterLabel(f, catalog?.fields || [])} ×
          </button>
        ))}
        {(config.filters.length > 0 ||
          config.universe.source === "WATCHLIST" ||
          raw.trim()) && (
          <button
            className="derivative-clear-all"
            onClick={() => {
              setConfig(initial);
              setRaw("");
              setEligible(null);
              setEligibilityStatus("idle");
              setRun(null);
              setSelected(null);
              setChecked([]);
            }}
          >
            Clear All
          </button>
        )}
      </div>
      <div
        className={`sc-grid conditional-detail-layout${panel ? " has-detail" : ""}`}
      >
        <aside className="wl-card sc-builder derivative-builder">
          <h2>Build a futures scan</h2>
          <p>
            Select up to 50 eligible NSE underlyings, an expiry and explicit
            filters.
          </p>
          <div className="sc-universe-tabs">
            <button
              className={config.universe.source === "CUSTOM" ? "active" : ""}
              onClick={() => {
                setError("");
                setRun(null);
                setSelected(null);
                setChecked([]);
                setConfig((c) => ({
                  ...c,
                  universe: { source: "CUSTOM", symbols: [] },
                }));
              }}
            >
              Custom
            </button>
            <button
              className={config.universe.source === "WATCHLIST" ? "active" : ""}
              onClick={() => {
                setError("");
                setRun(null);
                setSelected(null);
                setChecked([]);
                setEligible(null);
                setEligibilityStatus("idle");
                setConfig((c) => ({
                  ...c,
                  universe: { source: "WATCHLIST", symbols: [] },
                }));
              }}
            >
              Watchlist
            </button>
          </div>
          {config.universe.source === "CUSTOM" ? (
            <label className="sc-label">
              NSE underlyings
              <textarea
                aria-label="NSE underlyings"
                value={raw}
                onChange={(e) => {
                  setRaw(e.target.value);
                  setRun(null);
                  setSelected(null);
                  setChecked([]);
                }}
                placeholder="NIFTY, RELIANCE, HDFCBANK"
              />
            </label>
          ) : (
            <>
              <p>
                {selectedList?.name || "Choose a watchlist"} ·{" "}
                {eligible
                  ? `${eligible.eligible}/${eligible.members} futures eligible`
                  : config.universe.watchlist_id
                    ? eligibilityStatus === "error"
                      ? "eligibility unavailable"
                      : "checking eligibility"
                    : "select from toolbar"}
              </p>
              {eligible?.excluded.length ? (
                <details>
                  <summary>{eligible.excluded.length} excluded</summary>
                  {eligible.excluded.join(", ")}
                </details>
              ) : null}
              {eligible && eligible.symbols.length > 50 && (
                <>
                  <small>
                    Choose up to 50 eligible underlyings (
                    {config.universe.symbols.length} selected). This watchlist
                    has {eligible.symbols.length}; none were auto-truncated.
                  </small>
                  <div
                    className="sc-members"
                    role="group"
                    aria-label="Select futures underlyings"
                  >
                    {eligible.symbols.map((symbol) => (
                      <label key={symbol}>
                        <input
                          type="checkbox"
                          checked={config.universe.symbols.includes(symbol)}
                          disabled={
                            !config.universe.symbols.includes(symbol) &&
                            config.universe.symbols.length >= 50
                          }
                          onChange={(event) =>
                            setConfig((current) => ({
                              ...current,
                              universe: {
                                ...current.universe,
                                symbols: event.target.checked
                                  ? [...current.universe.symbols, symbol]
                                  : current.universe.symbols.filter(
                                      (item) => item !== symbol,
                                    ),
                              },
                            }))
                          }
                        />
                        {symbol}
                      </label>
                    ))}
                  </div>
                </>
              )}
              {eligible && eligible.symbols.length <= 50 && (
                <small>
                  All {eligible.symbols.length} futures-eligible members
                  selected.
                </small>
              )}
            </>
          )}
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
              <option value="EXACT">Exact listed expiry</option>
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
          <details className="derivative-filter-editor" open>
            <summary>＋ Add Filter</summary>
            <label className="sc-label">
              Field
              <select value={field} onChange={(e) => editField(e.target.value)}>
                <option value="">Select field</option>
                {catalog &&
                  [...new Set(catalog.fields.map((x) => x.category))].map(
                    (category) => (
                      <optgroup key={category} label={category}>
                        {catalog.fields
                          .filter((x) => x.category === category)
                          .map((x) => (
                            <option key={x.field} value={x.field}>
                              {x.label}
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
                value={operator}
                disabled={!spec}
                onChange={(e) => setOperator(e.target.value)}
              >
                {spec?.operators.map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            {spec?.kind === "enum" ? (
              <label className="sc-label">
                Value
                <select
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                >
                  {spec.values?.map((x) => (
                    <option key={x}>{x}</option>
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
                      value={upper}
                      onChange={(e) => setUpper(e.target.value)}
                    />
                  </label>
                )}
              </>
            )}
            <button disabled={!spec} onClick={addFilter}>
              Add / update filter
            </button>
          </details>
          <div className="derivative-run">
            <button
              className="wl-primary"
              disabled={busy || selectedList?.enabled === false}
              onClick={() => void execute()}
            >
              {busy ? "Scanning…" : "Run Scan"}
            </button>
            <button
              onClick={() => {
                setConfig(initial);
                setRaw("");
                setRun(null);
                setSelected(null);
                setChecked([]);
                setEligible(null);
                setEligibilityStatus("idle");
              }}
            >
              Reset
            </button>
          </div>
          <small>
            Dhan NSE futures quotes · exact listed contracts · no synthetic
            fallback.
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
                    options={columns}
                    selected={visible}
                    onChange={(key, on) =>
                      setVisible((v) =>
                        on ? [...v, key as Column] : v.filter((x) => x !== key),
                      )
                    }
                  />
                  <label>
                    Sort{" "}
                    <select
                      value={sort}
                      onChange={(e) => setSort(e.target.value)}
                    >
                      <option value="canonical">Canonical</option>
                      {catalog?.fields
                        .filter((f) => f.kind !== "enum")
                        .map((f) => (
                          <option key={f.field} value={f.field}>
                            {f.label}
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
                  {(
                    [
                      ["requested", "Underlyings requested", "target"],
                      ["resolved", "Resolved", "check"],
                      ["contracts_evaluated", "Contracts evaluated", "stack"],
                      ["not_evaluated", "Not evaluated", "warning"],
                      ["matches", "Matches", "trophy"],
                    ] as const
                  ).map(([key, label, icon]) => (
                    <div
                      key={key}
                      className={`derivative-count-card derivative-count-${key}`}
                    >
                      <span className="derivative-count-icon">
                        <Icon name={icon} />
                      </span>
                      <span>
                        <small>{label}</small>
                        <strong>{run.counts[key]}</strong>
                      </span>
                    </div>
                  ))}
                </div>
                {run.counts.not_evaluated > 0 && (
                  <details className="sc-evidence-summary">
                    <summary>
                      Not evaluated: {run.counts.not_evaluated} · view reasons
                    </summary>
                    <ul>
                      {Object.entries(run.not_evaluated_reasons || {}).map(
                        ([code, count]) => (
                          <li key={code}>
                            {code.replaceAll("_", " ")} · {count}
                          </li>
                        ),
                      )}
                    </ul>
                  </details>
                )}
                <div
                  className="derivative-table-wrap"
                  role="region"
                  aria-label="Futures scan results, scroll horizontally if needed"
                  tabIndex={0}
                >
                  <table>
                    <thead>
                      <tr>
                        <th>
                          <input
                            type="checkbox"
                            aria-label="Select all futures matches"
                            checked={
                              visibleRows.length > 0 &&
                              visibleRows.every((r) =>
                                checked.includes(r.contract.canonical_id),
                              )
                            }
                            onChange={(e) =>
                              setChecked(
                                e.target.checked
                                  ? visibleRows.map(
                                      (r) => r.contract.canonical_id,
                                    )
                                  : [],
                              )
                            }
                          />
                        </th>
                        <th>#</th>
                        {columns
                          .filter(([key]) => visible.includes(key))
                          .map(([key, label]) => (
                            <th key={key}>{label}</th>
                          ))}
                        {showAll && <th>Evaluation</th>}
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRows.map((row, index) => (
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
                              aria-label={`Select ${row.contract.trading_symbol}`}
                              checked={checked.includes(
                                row.contract.canonical_id,
                              )}
                              onChange={(e) =>
                                setChecked((ids) =>
                                  e.target.checked
                                    ? [...ids, row.contract.canonical_id]
                                    : ids.filter(
                                        (x) => x !== row.contract.canonical_id,
                                      ),
                                )
                              }
                            />
                          </td>
                          <td>{index + 1}</td>
                          {columns
                            .filter(([key]) => visible.includes(key))
                            .map(([key]) => (
                              <td key={key}>{cell(row, key)}</td>
                            ))}
                          {showAll && (
                            <td>
                              <strong>
                                {row.outcome.replaceAll("_", " ")}
                              </strong>
                              {row.evaluation_reason && (
                                <small className="sc-evidence-reason">
                                  {row.evaluation_reason.detail}
                                </small>
                              )}
                            </td>
                          )}
                          <td>
                            <div className="sc-row-actions derivative-row-actions">
                              <button
                                onClick={() => {
                                  setSelected(row);
                                  setPanel("detail");
                                }}
                              >
                                Why?
                              </button>
                              <button
                                disabled
                                title="No exact futures analytics route is available"
                              >
                                Analytics
                              </button>
                              <button
                                className="wl-buy"
                                disabled={
                                  !broker ||
                                  !row.contract.lot_size ||
                                  !row.contract.tick_size
                                }
                                title={
                                  broker
                                    ? "Open TWF Order preview for exact contract"
                                    : "Connect a futures-capable broker"
                                }
                                onClick={() => void trade(row, "BUY")}
                              >
                                B
                              </button>
                              <button
                                className="wl-sell"
                                disabled={
                                  !broker ||
                                  !row.contract.lot_size ||
                                  !row.contract.tick_size
                                }
                                title={
                                  broker
                                    ? "Open TWF Order preview for exact contract"
                                    : "Connect a futures-capable broker"
                                }
                                onClick={() => void trade(row, "SELL")}
                              >
                                S
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!visibleRows.length && (
                  <div className="sc-empty">
                    <h3>
                      {run.counts.contracts_evaluated > 0
                        ? "No contracts matched these filters."
                        : run.counts.not_evaluated > 0
                          ? "Contracts could not be evaluated because required evidence was unavailable."
                          : "No futures contracts were resolved."}
                    </h3>
                    <p>
                      {run.counts.not_evaluated > 0
                        ? "Show non-matches / not evaluated or review underlying diagnostics for details."
                        : "Review the selected universe and explicit filters."}
                    </p>
                  </div>
                )}
                {run.underlyings.length > 0 && (
                  <details className="sc-evidence-summary">
                    <summary>
                      Underlying diagnostics · {run.underlyings.length}{" "}
                      candidates
                    </summary>
                    <ul>
                      {run.underlyings.map((u) => (
                        <li key={u.symbol}>
                          <strong>{u.symbol}</strong> ·{" "}
                          {u.contract_id || "Contract missing"} ·{" "}
                          {u.outcome.replaceAll("_", " ")}
                          {u.evaluation_reason
                            ? ` · ${u.evaluation_reason.detail}`
                            : u.failure
                              ? ` · ${u.failure.replaceAll("_", " ")}`
                              : ""}
                          {u.evidence_status && (
                            <small className="sc-evidence-reason">
                              {Object.entries(u.evidence_status)
                                .map(([field, state]) => `${field}: ${state}`)
                                .join(" · ")}
                            </small>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <small>
                  Volume/OI percentile: current scan comparable futures; minimum
                  five valid contracts. ΔOI compares the same contract across
                  scans within 30 minutes. Spot direction uses Dhan 1D quote
                  change. Basis needs contemporaneous provider timestamps.
                </small>
              </>
            ) : (
              <div className="sc-empty">
                <h2>
                  {config.universe.source === "CUSTOM" &&
                  !symbolsFrom(raw).length
                    ? "Select a universe"
                    : config.universe.source === "WATCHLIST" &&
                        !config.universe.watchlist_id
                      ? "Select a watchlist"
                      : "Ready to scan"}
                </h2>
                <p>
                  {config.universe.source === "CUSTOM"
                    ? symbolsFrom(raw).length
                      ? "Custom underlyings are selected. Add explicit filters, then Run Scan."
                      : "Enter custom underlyings or choose a watchlist."
                    : config.universe.watchlist_id
                      ? "Watchlist selected. Review eligibility, add explicit filters, then Run Scan."
                      : "Choose a watchlist from the toolbar above."}
                </p>
              </div>
            )}
          </section>
          <div
            className="wl-card sc-bulk derivative-bulk"
            aria-label="Futures selection actions"
          >
            <span>{checked.length} selected</span>
            <button
              disabled
              title="Exact futures watchlist item add is deferred"
            >
              ＋ Add Selected to Watchlist
            </button>
            <button onClick={exportCsv} disabled={!checked.length}>
              Export CSV
            </button>
            <button disabled title="Exact futures chart is unavailable">
              Open in Chart
            </button>
            <button disabled title="Futures comparison is unavailable">
              Compare
            </button>
          </div>
        </main>
        {panel && (
          <aside className="wl-card derivative-detail sc-context-panel">
            <div className="sc-context-head">
              <h2>
                {panel === "detail"
                  ? "Instrument Analysis"
                  : panel === "saved"
                    ? "My Scans"
                    : panel === "movers"
                      ? "Market Movers"
                      : "Scan History"}
              </h2>
              <button onClick={() => setPanel(null)} aria-label="Close panel">
                ×
              </button>
            </div>
            {panel === "detail" && selected && (
              <>
                <h3>{selected.contract.trading_symbol}</h3>
                <p>
                  {selected.contract.instrument_type} · {selected.expiry} ·{" "}
                  {selected.outcome}
                </p>
                <strong>
                  ₹ {numeric(selected.observed.ltp)}{" "}
                  {signed(selected.observed.change_percent, "%")}
                </strong>
                <h3>Why?</h3>
                <p>{selected.reason}</p>
                {selected.outcome === "NOT_EVALUATED" &&
                  selected.evaluation_reasons && (
                    <ul className="derivative-diagnostics">
                      {selected.evaluation_reasons.map((item) => (
                        <li key={item.code}>
                          {item.code.replaceAll("_", " ")} · {item.detail}
                        </li>
                      ))}
                    </ul>
                  )}
                <ul className="derivative-diagnostics">
                  {selected.diagnostics.map((d) => (
                    <li key={d.filter.field}>
                      {d.passed === true
                        ? "Passed"
                        : d.passed === false
                          ? "Failed"
                          : "Unavailable"}{" "}
                      · {d.reason} · observed {d.observed ?? "unavailable"}
                    </li>
                  ))}
                </ul>
                <h3>Futures interpretation</h3>
                <p>
                  {selected.futures_interpretation.label} · inferred evidence ·{" "}
                  {selected.futures_interpretation.reason}
                </p>
                <p>
                  OI comparison:{" "}
                  {selected.comparison_window
                    ? `${selected.comparison_window.from} to ${selected.comparison_window.to}`
                    : "unavailable"}
                </p>
                <p>Basis: {selected.basis_reason}</p>
                <p>
                  Spot direction:{" "}
                  {selected.observed.underlying_trend || "unavailable"} (
                  {signed(selected.spot_change_percent, "%")}) · Dhan spot 1D
                  change
                </p>
                <p>
                  Source time: {selected.source_time || "unavailable"} ·
                  Received: {selected.received_at || "unavailable"}
                </p>
                <p>Missing: {selected.missing_evidence.join(", ") || "none"}</p>
                <div className="derivative-detail-actions">
                  <button disabled title="Exact futures analytics is deferred">
                    Analytics
                  </button>
                  <button disabled title="Exact futures chart is deferred">
                    Chart
                  </button>
                  <button
                    className="wl-buy"
                    disabled={!broker}
                    onClick={() => void trade(selected, "BUY")}
                  >
                    Buy
                  </button>
                  <button
                    className="wl-sell"
                    disabled={!broker}
                    onClick={() => void trade(selected, "SELL")}
                  >
                    Sell
                  </button>
                </div>
              </>
            )}
            {panel === "saved" && (
              <div className="sc-utility-list">
                {saved.length ? (
                  saved.map((item) => (
                    <article key={item.id}>
                      <strong>{item.config.name}</strong>
                      <small>FUTURES · {item.updated_at}</small>
                      <button onClick={() => load(item.config)}>
                        Use setup
                      </button>
                    </article>
                  ))
                ) : (
                  <p>No saved Futures scans yet.</p>
                )}
              </div>
            )}
            {(panel === "recent" || panel === "history") && (
              <div className="sc-utility-list">
                {history.length ? (
                  history.slice(0, panel === "recent" ? 5 : 50).map((item) => (
                    <article key={item.id}>
                      <strong>{item.config.name}</strong>
                      <small>
                        FUTURES · {item.counts.matches} matches ·{" "}
                        {item.created_at}
                      </small>
                      <button onClick={() => void view(item.id)}>View</button>
                      <button onClick={() => load(item.config)}>
                        Use setup
                      </button>
                    </article>
                  ))
                ) : (
                  <p>No Futures scans yet.</p>
                )}
              </div>
            )}
            {panel === "movers" && (
              <div className="sc-utility-list sc-movers">
                <p>TapTide · Optional market context. Load on demand.</p>
                <button
                  disabled={moversBusy}
                  onClick={() => {
                    setMoversBusy(true);
                    void scannerApi<ProviderResults>("movers")
                      .then((result) => {
                        setMovers(result);
                        setError("");
                      })
                      .catch((reason: Error) => setError(reason.message))
                      .finally(() => setMoversBusy(false));
                  }}
                >
                  {moversBusy ? "Loading…" : "Load movers"}
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
                      {movers.state} · {movers.coverage} · {movers.freshness}
                    </small>
                    {[...movers.rows]
                      .filter((row) =>
                        moverTab === "52W High"
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
                                "Symbol loaded. Run a Dhan Futures scan to check current eligibility and filters.",
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
                            {signed(row.metrics.change, "%")}
                          </span>
                        </article>
                      ))}
                  </>
                )}
              </div>
            )}
          </aside>
        )}
      </div>
      {ticket && (
        <OrderTicket
          destination="TWF_ORDER"
          origin={{ source: "SCANNER", reference: run!.id }}
          account={ticket.account}
          initial={{ instrument: ticket.instrument, side: ticket.side }}
          close={() => setTicket(null)}
        />
      )}
    </div>
  );
}
