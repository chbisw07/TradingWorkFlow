"use client";
import {
  useEffect,
  useState,
  cloneElement,
  type KeyboardEvent,
  type ReactElement,
} from "react";
import Link from "next/link";
import { SectorEvidence } from "./sector-evidence";
import {
  scannerApi,
  initialConfig,
  type Config,
  type Filter,
  type ContextFilter,
  type Catalog,
  type Run,
  type Saved,
  type ScanRow,
  type ProviderResults,
  type FilterField,
  fieldSpec,
  filterCompatible,
  filterExpression,
} from "../../lib/scanner";
import {
  watchApi,
  numberText,
  indianVolume,
  metadataMarketCap,
  changeText,
  type Watchlist,
  type WatchDetail,
  type WatchReference,
} from "../../lib/watchlists";
import { brokerApi, type Account, type Instrument } from "../../lib/brokers";
import { OrderTicket } from "../brokers/order-ticket";
import { MarketChart } from "../watchlists/market-chart";
import { WatchDialog } from "../watchlists/dialog";
import { Icon } from "../shell/icon";
import { InstrumentMetadataPanel } from "../instrument-metadata-panel";

const resultColumns = [
  ["volume", "Volume"],
  ["rsi", "RSI (14)"],
  ["trend", "Trend"],
  ["industry", "Industry"],
  ["marketCap", "Market Cap"],
  ["capCategory", "Cap Category"],
  ["twfTier", "TWF Tier"],
  ["chart", "Quick Chart (1M)"],
] as const;

export function ScannerWorkspace() {
  const [filterOpen, setFilterOpen] = useState(true);
  const [allHistory, setAllHistory] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  useEffect(() => {
    if (window.innerWidth <= 800) setFilterOpen(false);
  }, []);
  function tabKeys(e: KeyboardEvent<HTMLDivElement>) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    const tabs = Array.from(
      e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    );
    const index = tabs.indexOf(document.activeElement as HTMLButtonElement);
    const next =
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? tabs.length - 1
          : (index + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) %
            tabs.length;
    e.preventDefault();
    tabs[next]?.focus();
    tabs[next]?.click();
  }
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [config, setConfig] = useState<Config>(initialConfig);
  const [lists, setLists] = useState<Watchlist[]>([]),
    [members, setMembers] = useState<WatchDetail | null>(null);
  const [saved, setSaved] = useState<Saved[]>([]),
    [history, setHistory] = useState<Run[]>([]),
    [savedId, setSavedId] = useState("");
  const [run, setRun] = useState<Run | null>(null),
    [selected, setSelected] = useState<ScanRow | null>(null);
  const [checked, setChecked] = useState<string[]>([]),
    [target, setTarget] = useState(""),
    [addIds, setAddIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [derivatives, setDerivatives] = useState(false),
    [modal, setModal] = useState<"save" | "add" | "help" | "detail" | null>(
      null,
    );
  const [name, setName] = useState(""),
    [custom, setCustom] = useState(""),
    [search, setSearch] = useState("");
  const [view, setView] = useState("table"),
    [columns, setColumns] = useState(["volume", "rsi", "trend", "chart"]);
  const [sort, setSort] = useState("relevance"),
    [detailTab, setDetailTab] = useState("Overview"),
    [period, setPeriod] = useState("1M");
  const [reference, setReference] = useState<WatchReference | null>(null),
    [news, setNews] = useState<string[]>([]);
  const [movers, setMovers] = useState<ProviderResults | null>(null),
    [moverTab, setMoverTab] = useState("Top Gainers");
  const [accounts, setAccounts] = useState<Account[]>([]),
    [accountId, setAccountId] = useState("");
  const [ticket, setTicket] = useState<{
    account: Account;
    instrument: Instrument;
    side: "BUY" | "SELL";
  } | null>(null);
  const [field, setField] = useState("rsi"),
    [operator, setOperator] = useState("<"),
    [value, setValue] = useState("30"),
    [rhsMode, setRhsMode] = useState<"value" | "field">("value"),
    [comparisonField, setComparisonField] = useState(""),
    [lowerValue, setLowerValue] = useState("0"),
    [upperValue, setUpperValue] = useState("100");
  const [contextField, setContextField] = useState("vix_state"),
    [contextOperator, setContextOperator] = useState<"equals" | "not_equals">(
      "not_equals",
    ),
    [contextValue, setContextValue] = useState("HIGH");
  async function refresh() {
    const [c, l, s, h] = await Promise.all([
      scannerApi<Catalog>("catalog"),
      watchApi<Watchlist[]>(""),
      scannerApi<Saved[]>("saved"),
      scannerApi<Run[]>("runs"),
    ]);
    setCatalog(c);
    setLists(l.filter((x) => !x.archived && x.enabled !== false));
    setSaved(s);
    setHistory(h);
  }
  useEffect(() => {
    void refresh().catch((e) => setError(String(e.message)));
    void brokerApi<Account[]>("accounts")
      .then(setAccounts)
      .catch(() => {});
  }, []);
  useEffect(() => {
    let active = true;
    if (config.universe.source !== "WATCHLIST" || !config.universe.watchlist_id)
      return;
    void watchApi<WatchDetail>("/" + config.universe.watchlist_id)
      .then((x) => {
        if (!active) return;
        setMembers(x);
        if (x.items.length > 20) {
          setConfig((current) => {
            if (
              current.universe.source !== "WATCHLIST" ||
              current.universe.watchlist_id !== x.id ||
              current.universe.instrument_ids.length
            )
              return current;
            return {
              ...current,
              universe: {
                ...current.universe,
                instrument_ids: x.items
                  .slice(0, 20)
                  .map((item) => item.instrument.instrument_id),
              },
            };
          });
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [config.universe.source, config.universe.watchlist_id]);
  useEffect(() => {
    let active = true;
    if (!run || !selected?.instrument) return;
    const path = `runs/${run.id}/items/${selected.instrument.instrument_id}`;
    if (detailTab === "Fundamentals")
      void scannerApi<WatchReference>(path + "/reference")
        .then((x) => {
          if (active) setReference(x);
        })
        .catch(() => {
          if (active) setReference(null);
        });
    if (detailTab === "News")
      void scannerApi<{
        claims: {
          subject: string;
          provider: string;
          values: { headlines?: string[]; summary?: string };
        }[];
      }>(path + "/news")
        .then((x) => {
          if (active)
            setNews(
              x.claims.flatMap(
                (c) =>
                  c.values.headlines?.map((h) => c.provider + " · " + h) || [
                    c.provider +
                      " · " +
                      c.subject +
                      ": " +
                      (c.values.summary || "No normalized headline available."),
                  ],
              ),
            );
        })
        .catch(() => {
          if (active) setNews([]);
        });
    return () => {
      active = false;
    };
  }, [detailTab, selected, run]);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(t);
  }, [notice]);
  async function action(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request unavailable");
    } finally {
      setBusy(false);
    }
  }
  function loadTemplate(template: string) {
    const t = catalog?.templates.find((x) => x.name === template);
    if (t) {
      const nextSort =
        template === "Top Gainers" || template === "Top Losers"
          ? "change"
          : config.sort;
      setSort(nextSort);
      setConfig({
        ...config,
        name: t.name,
        filters: t.filters,
        sort: nextSort,
      });
    }
  }
  function loadConfig(c: Config, id = "") {
    const normalized: Config = {
      ...c,
      context_mode: c.context_mode || "RANKING",
      context_filters: c.context_filters || [],
      sort: c.sort || "relevance",
    };
    setSort(normalized.sort);
    setConfig(normalized);
    setCustom(normalized.universe.symbols.join(", "));
    setSavedId(id);
    setNotice(
      catalog && c.filters.every((item) => filterCompatible(item, catalog))
        ? "Scan setup loaded. Review filters before running."
        : "Legacy scan setup loaded. Correct incompatible filters before running.",
    );
  }
  function source(source: string) {
    setConfig({
      ...config,
      universe: { source, symbols: [], instrument_ids: [] },
    });
    setMembers(null);
  }
  function resetEditor(nextField: string) {
    const spec = fieldSpec(catalog, nextField);
    setField(nextField);
    setOperator(spec?.default_operator || ">");
    setValue(String(spec?.default_value ?? 0));
    setRhsMode("value");
    setComparisonField(spec?.comparison_fields[0] || "");
    const defaultNumber =
      typeof spec?.default_value === "number" ? spec.default_value : 0;
    const lower =
      spec?.minimum === undefined || spec.minimum === null
        ? defaultNumber
        : spec.minimum + (spec.minimum_exclusive ? 1 : 0);
    setLowerValue(String(lower));
    setUpperValue(
      String(spec?.maximum ?? Math.max(defaultNumber + 1, lower + 1)),
    );
  }
  function changeOperator(nextOperator: string) {
    const spec = fieldSpec(catalog, field);
    setOperator(nextOperator);
    setRhsMode("value");
    setComparisonField(spec?.comparison_fields[0] || "");
    setValue(String(spec?.default_value ?? 0));
    const defaultNumber =
      typeof spec?.default_value === "number" ? spec.default_value : 0;
    const lower =
      spec?.minimum === undefined || spec.minimum === null
        ? defaultNumber
        : spec.minimum + (spec.minimum_exclusive ? 1 : 0);
    setLowerValue(String(lower));
    setUpperValue(
      String(spec?.maximum ?? Math.max(defaultNumber + 1, lower + 1)),
    );
  }
  function addFilter(f = field) {
    const spec = fieldSpec(catalog, f);
    if (!spec) {
      setError("Choose a supported filter field.");
      return;
    }
    let nextValue: Filter["value"];
    if (operator === "between") {
      const lower = Number(lowerValue);
      const upper = Number(upperValue);
      if (!Number.isFinite(lower) || !Number.isFinite(upper)) {
        setError("Between needs two numeric values.");
        return;
      }
      nextValue = [lower, upper];
    } else if (rhsMode === "field") {
      if (!spec.comparison_fields.includes(comparisonField)) {
        setError("Choose a compatible comparison field.");
        return;
      }
      nextValue = comparisonField;
    } else if (spec.enum_values.length) {
      nextValue = value;
    } else {
      const numericValue = Number(value);
      if (!Number.isFinite(numericValue)) {
        setError("Enter a numeric value.");
        return;
      }
      nextValue = numericValue;
    }
    const nextFilter: Filter = {
      field: f,
      operator,
      value: nextValue,
      timeframe: "1d",
      version: "1",
      source: ["market_cap_inr", "pe_ratio"].includes(f)
        ? "tapetide"
        : "internal",
    };
    if (!filterCompatible(nextFilter, catalog)) {
      setError("Choose a value or comparison field allowed for this filter.");
      return;
    }
    setError("");
    setConfig({
      ...config,
      filters: [...config.filters, nextFilter],
    });
    setEditorOpen(false);
  }
  function selectContextField(next: string) {
    const spec = catalog?.context_fields?.find((item) => item.field === next);
    setContextField(next);
    setContextOperator(
      (spec?.default_operator || "equals") as "equals" | "not_equals",
    );
    setContextValue(String(spec?.default_value || spec?.enum_values[0] || ""));
  }
  function addContextFilter() {
    const spec = catalog?.context_fields?.find(
      (item) => item.field === contextField,
    );
    if (
      !spec ||
      spec.enabled === false ||
      !spec.enum_values.includes(contextValue)
    ) {
      setError("Choose a supported Market Context value.");
      return;
    }
    const next: ContextFilter = {
      field: contextField,
      operator: contextOperator,
      value: contextValue,
      source: "market_context",
      version: "1",
    };
    setConfig({
      ...config,
      context_mode: "HARD_FILTER",
      context_filters: [...(config.context_filters || []), next],
    });
    setError("");
  }
  async function execute() {
    await action(async () => {
      const c = {
        ...config,
        universe: {
          ...config.universe,
          symbols:
            config.universe.source === "CUSTOM"
              ? custom
                  .toUpperCase()
                  .split(/[\s,]+/)
                  .filter(Boolean)
              : [],
        },
      };
      const result = await scannerApi<Run>("runs", "POST", c);
      setRun(result);
      if (window.innerWidth <= 800) setFilterOpen(false);
      setSelected(null);
      setChecked([]);
      setSort(c.sort);
      await refresh();
      setNotice(
        `Scan completed: ${result.counts.matches} matches; ${result.counts.not_evaluated} not evaluated.`,
      );
    });
  }
  function inspect(row: ScanRow, tab = "Overview") {
    setSelected(row);
    setDetailTab(tab);
    setReference(null);
    setNews([]);
    if (window.innerWidth < 1200) setModal("detail");
  }
  const activeField = fieldSpec(catalog, field);
  const comparisonOptions = (activeField?.comparison_fields || [])
    .map((key) => fieldSpec(catalog, key))
    .filter((item): item is FilterField => Boolean(item && item.enabled));
  const filtersValid =
    !catalog || config.filters.every((item) => filterCompatible(item, catalog));
  const matches = (run?.rows || []).filter((r) => r.outcome === "MATCH");
  const rows = [...matches].sort((a, b) =>
    sort === "symbol"
      ? a.symbol.localeCompare(b.symbol)
      : sort === "relevance"
        ? Number(b.analysis?.final_relevance || 0) -
            Number(a.analysis?.final_relevance || 0) ||
          a.symbol.localeCompare(b.symbol)
        : Number(b.metrics?.[sort] || 0) - Number(a.metrics?.[sort] || 0) ||
          a.symbol.localeCompare(b.symbol),
  );
  const identity = (r: ScanRow) => r.instrument?.instrument_id || r.symbol;
  function addTo(ids: string[]) {
    setAddIds(ids);
    setTarget(lists[0]?.id || "new");
    setName("");
    setModal("add");
  }
  async function trade(row: ScanRow, side: "BUY" | "SELL") {
    await action(async () => {
      const account = accounts.find((a) => a.id === accountId);
      if (!account || !run) throw new Error("Select a connected broker.");
      const instrument = await scannerApi<Instrument>(
        `runs/${run.id}/items/${identity(row)}/broker-instrument?account_id=${account.id}`,
      );
      setModal(null);
      setTicket({ account, instrument, side });
    });
  }
  function csv() {
    if (!run) return;
    const text = [
      "Symbol,Provider,Completed close,1D %,Reason",
      ...matches.map((r) =>
        [
          r.symbol,
          "dhan",
          r.metrics?.price,
          r.metrics?.change,
          r.analysis?.short_reason ||
            r.diagnostics?.map((d) => d.reason).join("; "),
        ]
          .map((v) => '"' + String(v ?? "").replaceAll('"', '""') + '"')
          .join(","),
      ),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "scanner-results.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  const input = (
    label: string,
    content: ReactElement<{ "aria-label"?: string }>,
  ) => (
    <label className="sc-label">
      {label}
      {cloneElement(content, { "aria-label": label })}
    </label>
  );
  const detail = selected ? (
    <div className="sc-detail">
      <header>
        <strong>{selected.symbol}</strong>
        <div className="sc-detail-actions">
          <button disabled={busy} onClick={() => addTo([identity(selected)])}>
            ☆ Add to Watchlist
          </button>
          <button
            type="button"
            className="detail-panel-clear"
            aria-label="Clear selection"
            onClick={() => {
              setSelected(null);
              setModal(null);
            }}
          >
            Clear
          </button>
        </div>
      </header>
      <small>
        {selected.instrument?.exchange} · {selected.instrument?.segment} · Dhan
      </small>
      <small>
        LTP · Quote snapshot; change below uses completed daily bars
      </small>
      <p className="sc-price">
        {numberText(selected.quote ? Number(selected.quote.last_price) : null)}{" "}
        <span
          className={
            Number(selected.metrics?.change) > 0
              ? "up"
              : Number(selected.metrics?.change) < 0
                ? "down"
                : ""
          }
        >
          {changeText(selected.metrics?.change as number)}
        </span>
      </p>
      <small>
        {selected.quote
          ? `Quote received ${new Date(selected.quote.received_at).toLocaleString()}`
          : "Quote unavailable"}
      </small>
      <div
        role="tablist"
        onKeyDown={tabKeys}
        aria-label="Result analysis"
        className="sc-tabs"
      >
        {["Overview", "Evidence", "Fundamentals", "News"].map((t) => (
          <button
            role="tab"
            aria-selected={detailTab === t}
            key={t}
            onClick={() => setDetailTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={detailTab}>
        {detailTab === "Overview" ? (
          <>
            <div className="sc-periods">
              {["1W", "1M", "3M", "1Y"].map((p) => (
                <button
                  key={p}
                  aria-pressed={period === p}
                  onClick={() => setPeriod(p)}
                >
                  {p}
                </button>
              ))}
            </div>
            <MarketChart
              bars={(selected.bars || []).slice(
                -({ "1W": 5, "1M": 22, "3M": 66, "1Y": 252 }[period] || 22),
              )}
            />
            <small>As scanned · completed daily bars</small>
            <h3>Key data & technicals</h3>
            <dl className="sc-metrics">
              {[
                "price",
                "change",
                "volume",
                "rsi",
                "trend",
                "sma20",
                "sma50",
                "adx",
                "supertrend",
              ].map((k) => (
                <div key={k}>
                  <dt>
                    {catalog?.fields.find((f) => f.field === k)?.label || k}
                  </dt>
                  <dd>
                    {k === "volume"
                      ? indianVolume(selected.metrics?.[k] as number)
                      : typeof selected.metrics?.[k] === "number"
                        ? numberText(selected.metrics[k] as number)
                        : (selected.metrics?.[k] ?? "—")}
                  </dd>
                </div>
              ))}
            </dl>
            <InstrumentMetadataPanel metadata={selected.instrument_metadata} />
            <h3>Why matched</h3>
            <ul>
              {selected.diagnostics?.map((d, i) => (
                <li key={i}>
                  {d.reason} · observed{" "}
                  {typeof d.observed === "number"
                    ? numberText(d.observed)
                    : String(d.observed)}
                </li>
              ))}
            </ul>
            <details>
              <summary>Data details</summary>
              <p>{selected.basis}</p>
              <p>Source: {selected.source_time || "Unavailable"}</p>
              <p>Received: {selected.received_at || "Unavailable"}</p>
              <p>Run: {run?.id} · Provider: Dhan · REAL</p>
            </details>
          </>
        ) : detailTab === "Evidence" ? (
          selected.analysis ? (
            <div
              className="sc-analysis"
              aria-label="Deterministic candidate analysis"
            >
              <section>
                <h3>Ranking</h3>
                <dl className="sc-metrics">
                  <div>
                    <dt>Technical score</dt>
                    <dd>{selected.analysis.technical_score}</dd>
                  </div>
                  <div>
                    <dt>Context adjustment</dt>
                    <dd>
                      {selected.analysis.context_adjustment > 0 ? "+" : ""}
                      {selected.analysis.context_adjustment}
                    </dd>
                  </div>
                  <div>
                    <dt>Final relevance</dt>
                    <dd>{selected.analysis.final_relevance}</dd>
                  </div>
                  <div>
                    <dt>Setup direction</dt>
                    <dd>
                      {selected.analysis.setup_direction.replaceAll("_", " ")}
                    </dd>
                  </div>
                  <div>
                    <dt>Classification</dt>
                    <dd>
                      {selected.analysis.context_classification.replaceAll(
                        "_",
                        " ",
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Context coverage</dt>
                    <dd>{selected.analysis.context_coverage}</dd>
                  </div>
                </dl>
                <small>
                  Technical score is the V1 deterministic match baseline, not a
                  probability.
                </small>
              </section>
              <section>
                <h3>Technical setup</h3>
                <ul>
                  {selected.diagnostics?.map((item, index) => (
                    <li key={index}>
                      {item.reason} · observed{" "}
                      {String(item.observed ?? "unavailable")}
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h3>Market context contributions</h3>
                <div className="sc-context-list">
                  {selected.analysis.context_contributions.map((item) => (
                    <article key={item.factor}>
                      <strong>{item.factor.replaceAll("_", " ")}</strong>
                      <span
                        className={
                          item.contribution > 0
                            ? "up"
                            : item.contribution < 0
                              ? "down"
                              : ""
                        }
                      >
                        {item.contribution > 0 ? "+" : ""}
                        {item.contribution}
                      </span>
                      <p>
                        {item.observed_state.replaceAll("_", " ")} ·{" "}
                        {item.explanation}
                      </p>
                      <small>
                        {item.source || "Source unavailable"} · {item.freshness}
                      </small>
                    </article>
                  ))}
                </div>
              </section>
              {selected.analysis.sector_context && (
                <SectorEvidence evidence={selected.analysis.sector_context} />
              )}
              <section>
                <h3>Supporting factors</h3>
                {selected.analysis.supporting_factors.length ? (
                  <ul>
                    {selected.analysis.supporting_factors.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>None from available evidence.</p>
                )}
              </section>
              <section>
                <h3>Contradictions</h3>
                {selected.analysis.contradicting_factors.length ? (
                  <ul>
                    {selected.analysis.contradicting_factors.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No adverse contribution recorded.</p>
                )}
              </section>
              <section>
                <h3>Missing evidence</h3>
                {selected.analysis.missing_evidence.length ? (
                  <ul>
                    {selected.analysis.missing_evidence.map((item) => (
                      <li key={item}>{item.replaceAll("_", " ")}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No V1 dimension is missing.</p>
                )}
              </section>
              {selected.analysis.context_filter_diagnostics.length > 0 && (
                <section>
                  <h3>Hard filter checks</h3>
                  <ul>
                    {selected.analysis.context_filter_diagnostics.map(
                      (item) => (
                        <li key={item.reason}>
                          {item.passed ? "Passed" : "Failed"} · {item.reason} ·
                          observed {item.observed}
                        </li>
                      ),
                    )}
                  </ul>
                </section>
              )}
              <details>
                <summary>Provenance and freshness</summary>
                {selected.analysis.provenance.map((item) => (
                  <p key={item.dimension}>
                    {item.dimension.replaceAll("_", " ")} ·{" "}
                    {item.provider || "unavailable"}
                    {item.provider_tool
                      ? ` / ${item.provider_tool}`
                      : ""} · {item.freshness}
                  </p>
                ))}
              </details>
            </div>
          ) : (
            <p>
              Stored deterministic analysis is unavailable for this legacy run.
            </p>
          )
        ) : detailTab === "Fundamentals" ? (
          <>
            <h3>TapTide reference data</h3>
            {reference ? (
              <dl className="sc-metrics">
                <div>
                  <dt>Market cap (INR)</dt>
                  <dd>{numberText(reference.market_cap_inr)}</dd>
                </div>
                <div>
                  <dt>PE</dt>
                  <dd>{numberText(reference.pe_ratio)}</dd>
                </div>
              </dl>
            ) : (
              <p>Reference data unavailable or loading.</p>
            )}
            <p>Optional reference; does not alter technical scan results.</p>
          </>
        ) : (
          <>
            <h3>News & context</h3>
            {news.length ? (
              news.map((n, i) => <p key={i}>{n}</p>)
            ) : (
              <p>
                No normalized news available. Technical evidence remains
                Dhan-backed.
              </p>
            )}
          </>
        )}
      </div>
      <h3>Quick actions</h3>
      {input(
        "Broker",
        <select
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
        >
          <option value="">Select broker</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>,
      )}
      <div className="sc-trade">
        <button
          className="wl-buy"
          disabled={
            busy || !accountId || selected.instrument?.segment === "INDEX"
          }
          onClick={() => void trade(selected, "BUY")}
        >
          Buy
        </button>
        <button
          className="wl-sell"
          disabled={
            busy || !accountId || selected.instrument?.segment === "INDEX"
          }
          onClick={() => void trade(selected, "SELL")}
        >
          Sell
        </button>
      </div>
      <small>Opens Broker V2 preview. Confirmation is required.</small>
    </div>
  ) : null;
  return (
    <section className="watchlists-workspace scanner-v2">
      <header className="sc-page-head">
        <div>
          <h1>Scanners</h1>
          <p>
            Find opportunities using explicit filters, your watchlists, and
            market evidence.
          </p>
        </div>
        <Link href="/settings#integrations">Provider connections</Link>
      </header>
      {error && (
        <div role="alert" className="wl-error">
          {error}
          <button aria-label="Dismiss error" onClick={() => setError("")}>
            ×
          </button>
        </div>
      )}
      {notice && (
        <div role="status" className="wl-toast">
          {notice}
        </div>
      )}
      <div className="sc-top wl-card">
        <div
          className="sc-type-tabs"
          role="tablist"
          onKeyDown={tabKeys}
          aria-label="Scanner type"
        >
          <button
            role="tab"
            aria-selected={!derivatives}
            onClick={() => setDerivatives(false)}
          >
            <strong>Equity / Index Scanner</strong>
            <small>Stocks, indices, price & technical scans</small>
          </button>
          <button
            role="tab"
            aria-selected={derivatives}
            onClick={() => setDerivatives(true)}
          >
            <strong>Derivatives Scanner</strong>
            <small>Futures, options · planned</small>
          </button>
        </div>
        <div className="sc-top-actions">
          <select
            aria-label="Scan Templates"
            value=""
            onChange={(e) => loadTemplate(e.target.value)}
          >
            <option value="">Scan Templates</option>
            {catalog?.templates.map((t) => (
              <option key={t.name}>{t.name}</option>
            ))}
          </select>
          <a href="#sc-saved">My Scans</a>
          <a href="#sc-history" onClick={() => setAllHistory(true)}>
            Scan History
          </a>
          <button onClick={() => setModal("help")}>Help</button>
          <button
            className="wl-primary"
            onClick={() => {
              setName(config.name);
              setModal("save");
            }}
          >
            ＋ Save Scan
          </button>
        </div>
      </div>
      {derivatives ? (
        <div className="wl-card sc-empty">
          <h2>Derivatives Scanner</h2>
          <p>
            Expiry, liquidity, OI, IV and Greeks need a separate verified scan
            contract. Derivative analytics are not available in this version.
          </p>
          <button onClick={() => setDerivatives(false)}>
            Return to Equity / Index Scanner
          </button>
        </div>
      ) : (
        <div
          className={`sc-grid conditional-detail-layout${selected ? " has-detail" : ""}`}
        >
          <aside className="wl-card sc-builder">
            <details
              open={filterOpen}
              onToggle={(e) => setFilterOpen(e.currentTarget.open)}
            >
              <summary>Universe & filters</summary>
              <h2>Universe</h2>
              <div className="sc-universe-tabs">
                {["WATCHLIST", "INDEX", "SECTOR", "MARKET", "CUSTOM"].map(
                  (s) => (
                    <button
                      key={s}
                      aria-pressed={config.universe.source === s}
                      onClick={() => source(s)}
                    >
                      {s[0] + s.slice(1).toLowerCase()}
                    </button>
                  ),
                )}
              </div>
              {config.universe.source === "WATCHLIST" ? (
                <>
                  {input(
                    "Watchlist",
                    <select
                      value={config.universe.watchlist_id || ""}
                      onChange={(e) => {
                        setConfig({
                          ...config,
                          universe: {
                            source: "WATCHLIST",
                            watchlist_id: e.target.value,
                            symbols: [],
                            instrument_ids: [],
                          },
                        });
                        setMembers(null);
                      }}
                    >
                      <option value="">Choose watchlist</option>
                      <optgroup label="My Watchlists">
                        {lists
                          .filter((l) => l.ownership_kind !== "SYSTEM")
                          .map((l) => (
                            <option value={l.id} key={l.id}>
                              {l.name} ({l.count} symbols)
                            </option>
                          ))}
                      </optgroup>
                      <optgroup label="Built-in Watchlists">
                        {lists
                          .filter((l) => l.ownership_kind === "SYSTEM")
                          .map((l) => (
                            <option value={l.id} key={l.id}>
                              {l.name} · Built-in ({l.count} constituents)
                            </option>
                          ))}
                      </optgroup>
                    </select>,
                  )}
                  <input
                    aria-label="Search universe"
                    placeholder="Search watchlist…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                  <div className="sc-members">
                    {members?.items
                      .filter((i) =>
                        i.instrument.symbol.includes(search.toUpperCase()),
                      )
                      .map((i) => (
                        <label key={i.instrument.instrument_id}>
                          <input
                            type="checkbox"
                            checked={
                              !config.universe.instrument_ids.length ||
                              config.universe.instrument_ids.includes(
                                i.instrument.instrument_id,
                              )
                            }
                            onChange={(e) => {
                              const all = members.items.map(
                                (m) => m.instrument.instrument_id,
                              );
                              const ids = config.universe.instrument_ids.length
                                ? config.universe.instrument_ids
                                : all;
                              if (!e.target.checked && ids.length === 1) {
                                setError(
                                  "Keep at least one instrument selected.",
                                );
                                return;
                              }
                              if (
                                e.target.checked &&
                                !ids.includes(i.instrument.instrument_id) &&
                                ids.length >= 20
                              ) {
                                setError("Select no more than 20 instruments.");
                                return;
                              }
                              setConfig({
                                ...config,
                                universe: {
                                  ...config.universe,
                                  instrument_ids: e.target.checked
                                    ? Array.from(
                                        new Set([
                                          ...ids,
                                          i.instrument.instrument_id,
                                        ]),
                                      )
                                    : ids.filter(
                                        (x) => x !== i.instrument.instrument_id,
                                      ),
                                },
                              });
                            }}
                          />
                          {i.instrument.symbol}
                          <small>{i.kind}</small>
                        </label>
                      ))}
                  </div>
                  <small>
                    Snapshot captured when you run. Maximum 20 instruments.
                  </small>
                </>
              ) : config.universe.source === "CUSTOM" ? (
                input(
                  "NSE symbols",
                  <textarea
                    rows={4}
                    placeholder="RELIANCE, INFY, M&M"
                    value={custom}
                    onChange={(e) => setCustom(e.target.value)}
                  />,
                )
              ) : (
                <p>{catalog?.universe_limitation}</p>
              )}
              <h2>Scan Filters</h2>
              {Array.from(new Set(catalog?.fields.map((f) => f.category))).map(
                (category) => (
                  <details className="sc-category" key={category}>
                    <summary>{category}</summary>
                    {catalog?.fields
                      .filter((f) => f.category === category)
                      .map((f) => (
                        <button
                          key={f.field}
                          disabled={f.enabled === false}
                          onClick={() => {
                            setEditorOpen(true);
                            resetEditor(f.field);
                            requestAnimationFrame(() =>
                              document
                                .getElementById("sc-filter-editor")
                                ?.focus(),
                            );
                          }}
                        >
                          {f.label}
                        </button>
                      ))}
                  </details>
                ),
              )}
              <details className="sc-category sc-context-builder">
                <summary>Market Context</summary>
                <p>
                  Rank technical matches with a stored, explainable market
                  snapshot. Missing context never becomes positive evidence.
                </p>
                <fieldset>
                  <legend>Context mode</legend>
                  <div className="sc-context-modes">
                    {(["OFF", "RANKING", "HARD_FILTER"] as const).map(
                      (mode) => (
                        <button
                          type="button"
                          aria-pressed={config.context_mode === mode}
                          key={mode}
                          onClick={() =>
                            setConfig({
                              ...config,
                              context_mode: mode,
                              context_filters:
                                mode === "HARD_FILTER"
                                  ? config.context_filters || []
                                  : [],
                            })
                          }
                        >
                          {mode === "HARD_FILTER"
                            ? "Hard filter"
                            : mode[0] + mode.slice(1).toLowerCase()}
                        </button>
                      ),
                    )}
                  </div>
                  <small>
                    Ranking is the default. Only explicit predicates in Hard
                    filter mode can reject a technical match.
                  </small>
                </fieldset>
                {config.context_mode === "HARD_FILTER" && (
                  <fieldset>
                    <legend>Add context predicate</legend>
                    {input(
                      "Context field",
                      <select
                        value={contextField}
                        onChange={(event) =>
                          selectContextField(event.target.value)
                        }
                      >
                        {(catalog?.context_fields || []).map((item) => (
                          <option
                            value={item.field}
                            key={item.field}
                            disabled={item.enabled === false}
                          >
                            {item.label}
                          </option>
                        ))}
                      </select>,
                    )}
                    {input(
                      "Context operator",
                      <select
                        value={contextOperator}
                        onChange={(event) =>
                          setContextOperator(
                            event.target.value as "equals" | "not_equals",
                          )
                        }
                      >
                        <option value="equals">=</option>
                        <option value="not_equals">≠</option>
                      </select>,
                    )}
                    {input(
                      "Context value",
                      <select
                        value={contextValue}
                        onChange={(event) =>
                          setContextValue(event.target.value)
                        }
                      >
                        {(
                          catalog?.context_fields?.find(
                            (item) => item.field === contextField,
                          )?.enum_values || []
                        ).map((item) => (
                          <option value={item} key={item}>
                            {item.replaceAll("_", " ")}
                          </option>
                        ))}
                      </select>,
                    )}
                    <button
                      type="button"
                      disabled={
                        !(catalog?.context_fields || []).length ||
                        (config.context_filters || []).length >= 9
                      }
                      onClick={addContextFilter}
                    >
                      ＋ Add Context Filter
                    </button>
                  </fieldset>
                )}
              </details>
              <details
                open={editorOpen}
                onToggle={(e) => setEditorOpen(e.currentTarget.open)}
                className="sc-editor"
              >
                <summary>＋ Add / edit filter</summary>
                <fieldset id="sc-filter-editor" tabIndex={-1}>
                  <legend>Add filter</legend>
                  {input(
                    "Field",
                    <select
                      value={field}
                      onChange={(e) => resetEditor(e.target.value)}
                    >
                      {catalog?.fields.map((f) => (
                        <option
                          disabled={f.enabled === false}
                          value={f.field}
                          key={f.field}
                        >
                          {f.label}
                        </option>
                      ))}
                    </select>,
                  )}
                  {input(
                    "Operator",
                    <select
                      value={operator}
                      onChange={(e) => changeOperator(e.target.value)}
                    >
                      {(activeField?.operators || []).map((item) => (
                        <option value={item} key={item}>
                          {item === "equals"
                            ? "="
                            : item === "not_equals"
                              ? "≠"
                              : item.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>,
                  )}
                  {input(
                    "Compare to",
                    <select
                      value={rhsMode}
                      onChange={(e) => {
                        const mode = e.target.value as "value" | "field";
                        setRhsMode(mode);
                        setValue(String(activeField?.default_value ?? 0));
                        setComparisonField(
                          activeField?.comparison_fields[0] || "",
                        );
                      }}
                    >
                      <option value="value">Value</option>
                      {operator !== "between" &&
                        !activeField?.enum_values.length &&
                        comparisonOptions.length > 0 && (
                          <option value="field">Field</option>
                        )}
                    </select>,
                  )}
                  {operator === "between" ? (
                    <div className="sc-range-values">
                      {input(
                        "Lower value",
                        <input
                          type="number"
                          step="any"
                          min={activeField?.minimum ?? undefined}
                          max={activeField?.maximum ?? undefined}
                          value={lowerValue}
                          onChange={(e) => setLowerValue(e.target.value)}
                        />,
                      )}
                      {input(
                        "Upper value",
                        <input
                          type="number"
                          step="any"
                          min={activeField?.minimum ?? undefined}
                          max={activeField?.maximum ?? undefined}
                          value={upperValue}
                          onChange={(e) => setUpperValue(e.target.value)}
                        />,
                      )}
                    </div>
                  ) : rhsMode === "field" ? (
                    input(
                      "Comparison field",
                      <select
                        value={comparisonField}
                        onChange={(e) => setComparisonField(e.target.value)}
                      >
                        {comparisonOptions.map((item) => (
                          <option value={item.field} key={item.field}>
                            {item.label}
                          </option>
                        ))}
                      </select>,
                    )
                  ) : activeField?.enum_values.length ? (
                    input(
                      "Value",
                      <select
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                      >
                        {activeField.enum_values.map((item) => (
                          <option value={item} key={item}>
                            {item}
                          </option>
                        ))}
                      </select>,
                    )
                  ) : (
                    input(
                      "Value",
                      <input
                        type="number"
                        step="any"
                        min={activeField?.minimum ?? undefined}
                        max={activeField?.maximum ?? undefined}
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                      />,
                    )
                  )}
                  <small>
                    {activeField?.field_type}
                    {activeField?.unit ? ` · ${activeField.unit}` : ""}
                    {activeField?.minimum_exclusive &&
                    activeField.minimum !== null
                      ? ` · greater than ${activeField.minimum}`
                      : ""}
                  </small>
                  <button
                    disabled={config.filters.length >= 12}
                    onClick={() => addFilter()}
                  >
                    ＋ Add Filter
                  </button>
                </fieldset>
              </details>
            </details>
            <div className="sc-run">
              <button
                className="wl-primary"
                disabled={
                  busy ||
                  !config.filters.length ||
                  !filtersValid ||
                  !["CUSTOM", "WATCHLIST"].includes(config.universe.source)
                }
                onClick={() => void execute()}
              >
                {busy ? "Working…" : "Run Scan"}
              </button>
              <button
                disabled={busy}
                onClick={() => {
                  setConfig(initialConfig);
                  setCustom("");
                  setSavedId("");
                }}
              >
                Reset
              </button>
            </div>
            <small>
              Dhan · real completed daily bars · no synthetic fallback
            </small>
          </aside>
          <main className="sc-center">
            <div className="wl-card sc-chips">
              <span>
                Universe:{" "}
                {config.universe.source === "WATCHLIST"
                  ? lists.find((l) => l.id === config.universe.watchlist_id)
                      ?.name || "Choose watchlist"
                  : config.universe.source}
              </span>
              {config.filters.map((f, i) => (
                <button
                  title="Remove filter"
                  aria-label={`Remove filter ${i + 1}`}
                  key={i}
                  onClick={() =>
                    setConfig({
                      ...config,
                      filters: config.filters.filter((_, j) => j !== i),
                    })
                  }
                >
                  {filterExpression(f, catalog)} ×
                </button>
              ))}
              <span className="sc-context-chip">
                Context:{" "}
                {(config.context_mode || "RANKING").replaceAll("_", " ")}
              </span>
              {(config.context_filters || []).map((item, index) => {
                const spec = catalog?.context_fields?.find(
                  (field) => field.field === item.field,
                );
                return (
                  <button
                    className="sc-context-chip"
                    title="Remove Market Context filter"
                    aria-label={`Remove context filter ${index + 1}`}
                    key={`${item.field}-${index}`}
                    onClick={() =>
                      setConfig({
                        ...config,
                        context_filters: config.context_filters.filter(
                          (_, current) => current !== index,
                        ),
                      })
                    }
                  >
                    {spec?.label || item.field}{" "}
                    {item.operator === "equals" ? "=" : "≠"}{" "}
                    {item.value.replaceAll("_", " ")} ×
                  </button>
                );
              })}
              <button onClick={() => setConfig({ ...config, filters: [] })}>
                Clear All
              </button>
              {!filtersValid && (
                <p role="alert">
                  This legacy setup contains incompatible filters. Remove or
                  replace them before running.
                </p>
              )}
            </div>
            <section className="wl-card sc-results">
              <header>
                <h2>
                  Scan Results <small>{matches.length} results</small>
                </h2>
                <details>
                  <summary>Columns</summary>
                  {resultColumns.map(([c, label]) => (
                    <label key={c}>
                      <input
                        type="checkbox"
                        checked={columns.includes(c)}
                        onChange={(e) =>
                          setColumns(
                            e.target.checked
                              ? [...columns, c]
                              : columns.filter((x) => x !== c),
                          )
                        }
                      />
                      {label}
                    </label>
                  ))}
                </details>
                <select
                  aria-label="Sort results"
                  value={sort}
                  onChange={(e) => setSort(e.target.value)}
                >
                  {["symbol", "relevance", "change", "volume", "rsi"].map(
                    (s) => (
                      <option key={s} value={s}>
                        Sort: {s}
                      </option>
                    ),
                  )}
                </select>
                <button
                  aria-pressed={view === "table"}
                  onClick={() => setView("table")}
                >
                  Table
                </button>
                <button
                  aria-pressed={view === "charts"}
                  onClick={() => setView("charts")}
                >
                  Charts
                </button>
              </header>
              {run && (
                <>
                  <div className="sc-counts">
                    {Object.entries(run.counts).map(([k, v]) => (
                      <span key={k}>
                        {k.replaceAll("_", " ")} <strong>{v}</strong>
                      </span>
                    ))}
                  </div>
                  <p className="sc-basis">
                    Dhan · Real · {new Date(run.created_at).toLocaleString()} ·{" "}
                    {run.config.name} · Indicators / 1D change: completed daily
                    bars · LTP: separate Dhan quote snapshot
                  </p>
                  {run.context_snapshot && (
                    <p className="sc-context-summary">
                      Shared market intelligence ·{" "}
                      {run.config.context_mode || "RANKING"} ·{" "}
                      {run.context_snapshot.status} · coverage{" "}
                      {run.context_snapshot.coverage_count}/
                      {run.context_snapshot.dimension_count} ·{" "}
                      {run.context_snapshot.provider || "provider unavailable"}.
                      Dhan sector context and combined coverage are shown per
                      result in Evidence.
                    </p>
                  )}
                  {(JSON.stringify(run.config.filters) !==
                    JSON.stringify(config.filters) ||
                    (run.config.context_mode || "RANKING") !==
                      (config.context_mode || "RANKING") ||
                    JSON.stringify(run.config.context_filters || []) !==
                      JSON.stringify(config.context_filters || []) ||
                    run.config.universe.source !== config.universe.source ||
                    (run.config.universe.watchlist_id || "") !==
                      (config.universe.watchlist_id || "") ||
                    JSON.stringify(
                      [...run.config.universe.instrument_ids].sort(),
                    ) !==
                      JSON.stringify(
                        [...config.universe.instrument_ids].sort(),
                      ) ||
                    (config.universe.source === "CUSTOM" &&
                      run.config.universe.symbols.join(",") !==
                        custom
                          .toUpperCase()
                          .split(/[\s,]+/)
                          .filter(Boolean)
                          .join(","))) && (
                    <p role="status">
                      Showing the previous scan. Current setup has not been run.
                    </p>
                  )}
                </>
              )}
              {!run ? (
                <div className="sc-empty">
                  <Icon name="scanners" />
                  <h2>Build your next scan</h2>
                  <p>
                    Choose a universe, load a template or add explicit filters,
                    then Run Scan.
                  </p>
                </div>
              ) : !matches.length ? (
                <div className="sc-empty">
                  <h3>No matches recorded</h3>
                  <p>
                    {run.counts.not_evaluated
                      ? "Some instruments could not be evaluated. Review diagnostics below."
                      : "All evaluated instruments failed at least one condition."}
                  </p>
                </div>
              ) : view === "charts" ? (
                <div className="sc-chart-grid">
                  {rows.map((r) => (
                    <button key={identity(r)} onClick={() => inspect(r)}>
                      <strong>{r.symbol}</strong>
                      <MarketChart bars={(r.bars || []).slice(-22)} />
                      <small>
                        {r.analysis?.short_reason ||
                          r.diagnostics?.map((d) => d.reason).join(" · ")}
                      </small>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="sc-table-wrap">
                  <table className="sc-table">
                    <thead>
                      <tr>
                        <th>
                          <input
                            aria-label="Select all results"
                            type="checkbox"
                            checked={
                              !!matches.length &&
                              checked.length === matches.length
                            }
                            onChange={(e) =>
                              setChecked(
                                e.target.checked ? matches.map(identity) : [],
                              )
                            }
                          />
                        </th>
                        <th>Symbol</th>
                        <th>Sector</th>
                        <th>LTP</th>
                        <th>1D %</th>
                        {columns.includes("volume") && <th>Volume</th>}
                        {columns.includes("rsi") && <th>RSI (14)</th>}
                        {columns.includes("trend") && <th>Trend</th>}
                        {columns.includes("industry") && <th>Industry</th>}
                        {columns.includes("marketCap") && <th>Market Cap</th>}
                        {columns.includes("capCategory") && (
                          <th>Cap Category</th>
                        )}
                        {columns.includes("twfTier") && <th>TWF Tier</th>}
                        {columns.includes("chart") && <th>Quick Chart (1M)</th>}
                        <th>Reason (Why Matched)</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={identity(r)}>
                          <td>
                            <input
                              aria-label={`Select ${r.symbol}`}
                              type="checkbox"
                              checked={checked.includes(identity(r))}
                              onChange={(e) =>
                                setChecked(
                                  e.target.checked
                                    ? [...checked, identity(r)]
                                    : checked.filter((x) => x !== identity(r)),
                                )
                              }
                            />
                          </td>
                          <td>
                            <button
                              className="sc-symbol"
                              onClick={() => inspect(r)}
                            >
                              {r.symbol}
                            </button>
                            <small>{r.instrument?.exchange}</small>
                          </td>
                          <td
                            data-label="Sector"
                            title={
                              r.instrument_metadata?.resolution_basis ===
                              "UNDERLYING"
                                ? `Underlying sector for ${r.instrument_metadata.metadata_symbol}`
                                : undefined
                            }
                          >
                            {r.instrument_metadata?.sector || "—"}
                          </td>
                          <td data-label="LTP">
                            {numberText(
                              r.quote ? Number(r.quote.last_price) : null,
                            )}
                          </td>
                          <td
                            data-label="1D %"
                            className={
                              Number(r.metrics?.change) > 0
                                ? "up"
                                : Number(r.metrics?.change) < 0
                                  ? "down"
                                  : ""
                            }
                          >
                            {changeText(r.metrics?.change as number)}
                          </td>
                          {columns.includes("volume") && (
                            <td data-label="Volume">
                              {indianVolume(r.metrics?.volume as number)}
                            </td>
                          )}
                          {columns.includes("rsi") && (
                            <td data-label="RSI (14)">
                              {numberText(r.metrics?.rsi as number)}
                            </td>
                          )}
                          {columns.includes("trend") && (
                            <td data-label="Trend">
                              <span className="sc-trend">
                                {r.metrics?.trend ?? "—"}
                              </span>
                            </td>
                          )}
                          {columns.includes("industry") && (
                            <td data-label="Industry">
                              {r.instrument_metadata?.industry || "—"}
                            </td>
                          )}
                          {columns.includes("marketCap") && (
                            <td data-label="Market Cap">
                              {metadataMarketCap(r.instrument_metadata)}
                            </td>
                          )}
                          {columns.includes("capCategory") && (
                            <td data-label="Cap Category">
                              {r.instrument_metadata?.market_cap_category ||
                                "—"}
                            </td>
                          )}
                          {columns.includes("twfTier") && (
                            <td data-label="TWF Tier">
                              {r.instrument_metadata?.twf_cap_tier || "—"}
                            </td>
                          )}
                          {columns.includes("chart") && (
                            <td data-label="1M chart">
                              <MarketChart
                                compact
                                bars={(r.bars || []).slice(-22)}
                              />
                            </td>
                          )}
                          <td>
                            <div className="sc-reason">
                              <span>
                                {r.analysis?.short_reason ||
                                  r.diagnostics
                                    ?.map((item) => item.reason)
                                    .join(" · ")}
                              </span>
                              <button
                                type="button"
                                onClick={() => inspect(r, "Evidence")}
                              >
                                Why?
                              </button>
                            </div>
                          </td>
                          <td>
                            <div className="sc-row-actions">
                              <button
                                title="Add to Watchlist"
                                aria-label={`Add ${r.symbol} to Watchlist`}
                                onClick={() => addTo([identity(r)])}
                              >
                                ＋
                              </button>
                              <button
                                aria-label={`Review ${r.symbol}`}
                                onClick={() => inspect(r)}
                              >
                                ↗
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {run && (
                <details className="sc-diagnostics">
                  <summary>
                    Per-symbol diagnostics · {run.rows.length} records
                  </summary>
                  {run.rows.map((r) => (
                    <div key={r.symbol}>
                      <strong>
                        {r.symbol} · {r.outcome.replaceAll("_", " ")}
                      </strong>
                      {r.failure && <p>{r.failure.replaceAll("_", " ")}</p>}
                      {r.diagnostics?.map((d, i) => (
                        <p key={i}>
                          {d.reason} · observed{" "}
                          {String(d.observed ?? "unavailable")} ·{" "}
                          {d.passed === null
                            ? "Not evaluated"
                            : d.passed
                              ? "Pass"
                              : "Fail"}
                        </p>
                      ))}
                    </div>
                  ))}
                </details>
              )}
            </section>
            <div className="wl-card sc-bulk">
              <span>{checked.length} selected</span>
              <button
                disabled={!checked.length || busy}
                onClick={() => addTo(checked)}
              >
                ＋ Add Selected to Watchlist
              </button>
              <button
                disabled={!matches.length || busy}
                onClick={() => addTo(matches.map(identity))}
              >
                Add All
              </button>
              <button disabled={!matches.length} onClick={csv}>
                Export CSV
              </button>
              <button
                disabled={!checked.length}
                onClick={() =>
                  inspect(matches.find((r) => identity(r) === checked[0])!)
                }
              >
                Open in Chart
              </button>
              <button disabled title="Comparison is planned">
                Compare
              </button>
            </div>
            <div className="sc-bottom">
              <section className="wl-card" id="sc-saved">
                <h2>Saved Scans</h2>
                {!saved.filter((s) => !s.archived).length && (
                  <p>No saved scans yet.</p>
                )}
                {saved
                  .filter((s) => !s.archived)
                  .map((s) => (
                    <article key={s.id}>
                      <button onClick={() => loadConfig(s.config, s.id)}>
                        <strong>{s.config.name}</strong>
                      </button>
                      <small>
                        {s.config.filters.length} filters ·{" "}
                        {s.config.universe.source}
                      </small>
                      <button
                        disabled={busy}
                        onClick={() => {
                          setSavedId(s.id);
                          setName(s.config.name);
                          loadConfig(s.config, s.id);
                          setModal("save");
                        }}
                      >
                        Edit
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          void action(async () => {
                            await scannerApi("saved/" + s.id, "PATCH", {
                              config: s.config,
                              archived: true,
                            });
                            await refresh();
                          })
                        }
                      >
                        Archive
                      </button>
                    </article>
                  ))}
              </section>
              <section className="wl-card" id="sc-history">
                <h2>{allHistory ? "Scan History" : "Recent Scans"}</h2>
                {history.length > 5 && (
                  <button onClick={() => setAllHistory(!allHistory)}>
                    {allHistory
                      ? "Show recent"
                      : `View all (${history.length})`}
                  </button>
                )}
                {!history.length && (
                  <p>
                    No Scanner V2 runs yet. Historical S&D remains in Discovery.
                  </p>
                )}
                {history.slice(0, allHistory ? 50 : 5).map((h) => (
                  <article key={h.id}>
                    <strong>{h.config.name}</strong>
                    <small>
                      {h.counts.matches} results ·{" "}
                      {new Date(h.created_at).toLocaleString()}
                    </small>
                    <button
                      onClick={() =>
                        void action(async () => {
                          setRun(await scannerApi<Run>("runs/" + h.id));
                          setSelected(null);
                          setChecked([]);
                        })
                      }
                    >
                      View
                    </button>
                    <button onClick={() => loadConfig(h.config)}>
                      Use setup
                    </button>
                  </article>
                ))}
              </section>
              <section className="wl-card sc-movers">
                <h2>
                  Market Movers <small>TapTide</small>
                </h2>
                <button
                  disabled={busy}
                  onClick={() =>
                    void action(async () =>
                      setMovers(await scannerApi<ProviderResults>("movers")),
                    )
                  }
                >
                  Load movers
                </button>
                <button
                  disabled={busy}
                  onClick={() =>
                    void action(async () =>
                      setMovers(
                        await scannerApi<ProviderResults>(
                          "provider-screen",
                          "POST",
                          {
                            ...config,
                            universe: {
                              source: "CUSTOM",
                              symbols: ["NIFTY"],
                              instrument_ids: [],
                            },
                          },
                        ),
                      ),
                    )
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
                  ].map((t) => (
                    <button
                      aria-pressed={moverTab === t}
                      key={t}
                      onClick={() => setMoverTab(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                {!movers ? (
                  <p>Optional provider-wide evidence. Load on demand.</p>
                ) : (
                  <>
                    <small>
                      {movers.tool === "screen_stocks_technical"
                        ? "Technical screen results · "
                        : ""}
                      {movers.state} · {movers.coverage} · {movers.freshness}
                    </small>
                    {[...movers.rows]
                      .filter((r) =>
                        movers.tool === "screen_stocks_technical"
                          ? true
                          : moverTab === "52W High"
                            ? (r.buckets || [r.bucket]).includes(
                                "near_52w_high",
                              )
                            : moverTab === "52W Low"
                              ? (r.buckets || [r.bucket]).includes(
                                  "near_52w_low",
                                )
                              : moverTab === "Top Gainers"
                                ? Number(r.metrics.change) > 0
                                : moverTab === "Top Losers"
                                  ? Number(r.metrics.change) < 0
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
                      .map((r) => (
                        <article key={r.symbol}>
                          <button
                            onClick={() => {
                              source("CUSTOM");
                              setCustom(r.symbol);
                              setNotice(
                                "Symbol loaded. Run the Dhan scan to evaluate your exact filters.",
                              );
                            }}
                          >
                            {r.symbol}
                          </button>
                          <span
                            className={
                              Number(r.metrics.change) > 0 ? "up" : "down"
                            }
                          >
                            {changeText(r.metrics.change)}
                          </span>
                        </article>
                      ))}
                  </>
                )}
              </section>
            </div>
          </main>
          {selected && <aside className="wl-card sc-inspector">{detail}</aside>}
        </div>
      )}
      {modal && (
        <WatchDialog
          title={
            modal === "save"
              ? "Save Scan"
              : modal === "add"
                ? "Add results to Watchlist"
                : modal === "help"
                  ? "Scanner help"
                  : "Result analysis"
          }
          close={() => setModal(null)}
        >
          {modal === "detail" ? (
            detail
          ) : modal === "help" ? (
            <>
              <p>
                All filters use AND logic and completed daily Dhan OHLCV. The
                selected field controls valid operators and whether the filter
                compares with a typed value or a compatible field. Between uses
                explicit lower and upper values.
              </p>
              <p>
                Failed acquisition is NOT_EVALUATED, never a non-match.
                Templates populate editable filters. Scanner results do not
                authorize a trade.
              </p>
              <p>
                TapTide screens are separate provider-wide samples. Discovery
                retains temporal interpretation and previous history.
              </p>
            </>
          ) : modal === "save" ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action(async () => {
                  const c = {
                    ...config,
                    name,
                    sort,
                    universe: {
                      ...config.universe,
                      symbols:
                        config.universe.source === "CUSTOM"
                          ? custom
                              .toUpperCase()
                              .split(/[\s,]+/)
                              .filter(Boolean)
                          : [],
                    },
                  };
                  await scannerApi(
                    savedId ? "saved/" + savedId : "saved",
                    savedId ? "PATCH" : "POST",
                    { config: c },
                  );
                  setConfig(c);
                  setModal(null);
                  await refresh();
                });
              }}
            >
              {input(
                "Scan name",
                <input
                  required
                  maxLength={80}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />,
              )}
              <button className="wl-primary" disabled={busy}>
                Save configuration
              </button>
              {savedId && (
                <button type="button" onClick={() => setSavedId("")}>
                  Save as new instead
                </button>
              )}
            </form>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action(async () => {
                  const destination =
                    target === "new"
                      ? (await watchApi<Watchlist>("", "POST", { name })).id
                      : target;
                  await scannerApi(
                    `runs/${run!.id}/watchlists/${destination}`,
                    "POST",
                    { instrument_ids: addIds },
                  );
                  setModal(null);
                  setNotice(
                    "Results added. Existing membership was preserved without duplicates.",
                  );
                  await refresh();
                });
              }}
            >
              {input(
                "Destination watchlist",
                <select
                  required
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  <option value="">Choose watchlist</option>
                  <option value="new">Create new watchlist</option>
                  {lists
                    .filter(
                      (l) => l.ownership_kind !== "SYSTEM" && !l.read_only,
                    )
                    .map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                </select>,
              )}
              {target === "new" &&
                input(
                  "New watchlist name",
                  <input
                    required
                    maxLength={80}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />,
                )}
              <p>
                {addIds.length} canonical instruments · Scanner provenance
                retained
              </p>
              <button disabled={busy || !target}>Add results</button>
              <Link href="/watchlists">Manage / create Watchlists</Link>
            </form>
          )}
        </WatchDialog>
      )}
      {ticket && (
        <OrderTicket
          account={ticket.account}
          initial={{ instrument: ticket.instrument, side: ticket.side }}
          close={() => setTicket(null)}
        />
      )}
    </section>
  );
}
