"use client";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useId,
  type ReactNode,
} from "react";
import { brokerApi, type Account, type Instrument } from "../../lib/brokers";
import { canOrder, type Capability, type Side } from "../../lib/broker-orders";
import {
  badge,
  change,
  changeText,
  label,
  numberText,
  indianVolume,
  indianMarketCap,
  previousClose,
  periodChange,
  sessionDate,
  type WatchReference,
  watchApi,
  type Kind,
  type WatchBar,
  type WatchChart,
  type WatchDetail,
  type WatchItem,
  type WatchMetrics,
  type Watchlist,
  type WatchQuote,
} from "../../lib/watchlists";
import { OrderTicket } from "../brokers/order-ticket";
import { WatchDialog } from "./dialog";
import { MarketChart } from "./market-chart";

const kinds: Kind[] = ["EQUITY", "OPTION", "FUTURE", "INDEX"];
const columns = [
  "LTP",
  "1D %",
  "Volume",
  "RSI (14)",
  "Trend",
  "Quick Chart (1M)",
];
const time = (v: string) =>
  new Date(v).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

export function WatchlistsWorkspace() {
  const panelId = useId();
  const [lists, setLists] = useState<Watchlist[]>([]),
    [selected, setSelected] = useState("");
  const [detail, setDetail] = useState<WatchDetail | null>(null),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false),
    [notice, setNotice] = useState("");
  const [listSearch, setListSearch] = useState(""),
    [trash, setTrash] = useState(false);
  const [query, setQuery] = useState(""),
    [type, setType] = useState<Kind | "ALL">("ALL");
  const [visible, setVisible] = useState(columns),
    [group, setGroup] = useState("none");
  const [minimum, setMinimum] = useState(""),
    [positive, setPositive] = useState(false),
    [minVolume, setMinVolume] = useState("");
  const [page, setPage] = useState(1),
    [pageSize, setPageSize] = useState(10),
    [checked, setChecked] = useState<string[]>([]);
  const [target, setTarget] = useState("");
  const [instrumentId, setInstrumentId] = useState(""),
    [mobilePanel, setMobilePanel] = useState(false);
  const [quotes, setQuotes] = useState<Record<string, WatchQuote>>({}),
    [quoteError, setQuoteError] = useState("");
  const [metrics, setMetrics] = useState<Record<string, WatchMetrics>>({});
  const [history, setHistory] = useState<Record<string, WatchBar[]>>({});
  const [auto, setAuto] = useState(false),
    [interval, setIntervalValue] = useState(15),
    [refreshing, setRefreshing] = useState(false);
  const quoteLock = useRef(false),
    scope = useRef(selected);
  useEffect(() => {
    scope.current = selected;
  }, [selected]);
  const [period, setPeriod] = useState("1M"),
    [chart, setChart] = useState<WatchChart | null>(null),
    [tab, setTab] = useState("Overview");
  const chartCache = useRef(
    new Map<string, { at: number; value: WatchChart }>(),
  );
  const chartRequests = useRef(new Map<string, Promise<WatchChart>>());
  const loadChart = useCallback((list: string, id: string, range: string) => {
    const key = `${list}:${id}:${range}`;
    const cached = chartCache.current.get(key);
    if (
      cached &&
      Date.now() - cached.at < (cached.value.error ? 30000 : 300000)
    )
      return Promise.resolve(cached.value);
    const pending = chartRequests.current.get(key);
    if (pending) return pending;
    const request = watchApi<WatchChart>(
      `/${list}/items/${id}/chart?period=${range}`,
    )
      .then((value) => {
        chartCache.current.set(key, { at: Date.now(), value });
        while (chartCache.current.size > 100)
          chartCache.current.delete(chartCache.current.keys().next().value!);
        return value;
      })
      .finally(() => chartRequests.current.delete(key));
    chartRequests.current.set(key, request);
    return request;
  }, []);
  const [accounts, setAccounts] = useState<Account[]>([]),
    [brokerId, setBrokerId] = useState("");
  const [quantity, setQuantity] = useState(1),
    [orderType, setOrderType] = useState("LIMIT");
  const [ticket, setTicket] = useState<{
    account: Account;
    instrument: Instrument;
    side: Side;
    quantity: number;
    orderType: string;
  } | null>(null);
  const [modal, setModal] = useState<
    "create" | "edit" | "add" | "import" | "archive" | null
  >(null);
  const [name, setName] = useState(""),
    [description, setDescription] = useState(""),
    [note, setNote] = useState("");
  const [search, setSearch] = useState(""),
    [searchKind, setSearchKind] = useState<Kind>("EQUITY"),
    [results, setResults] = useState<WatchItem[]>([]);
  const [csv, setCsv] = useState(""),
    [importResult, setImportResult] = useState<{
      added: number;
      duplicates: number;
      invalid: { row: number; symbol: string; reason: string }[];
    } | null>(null);
  const current = detail?.id === selected ? detail : null;
  const item = current?.items.find(
    (i) => i.instrument.instrument_id === instrumentId,
  );
  const quote = item ? quotes[item.instrument.instrument_id] : undefined;
  const account = accounts.find((a) => a.id === brokerId);
  const refreshLists = useCallback(async () => {
    const next = await watchApi<Watchlist[]>();
    setLists(next);
    setLoaded(true);
    return next;
  }, []);
  const refreshDetail = useCallback(async (id: string) => {
    const next = await watchApi<WatchDetail>(`/${id}`);
    if (scope.current === id) setDetail(next);
  }, []);
  useEffect(() => {
    const c = new AbortController();
    void watchApi<Watchlist[]>("", "GET", undefined, c.signal)
      .then((next) => {
        setLists(next);
        setSelected(next.find((l) => !l.archived)?.id || "");
        setLoaded(true);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoaded(true);
        }
      });
    void brokerApi<Account[]>("accounts", undefined, c.signal)
      .then(async (all) => {
        const connected = all.filter((a) => a.state === "connected");
        const eligible = await Promise.all(
          connected.map(async (a) => {
            try {
              const cap = await brokerApi<Capability>(
                `accounts/${a.id}/order-entry/capabilities`,
                undefined,
                c.signal,
              );
              return cap.enabled ? a : null;
            } catch {
              return null;
            }
          }),
        );
        if (!c.signal.aborted) {
          const valid = eligible.filter((a): a is Account => a !== null);
          setAccounts(valid);
          if (valid.length === 1) setBrokerId(valid[0].id);
        }
      })
      .catch(() => {});
    return () => c.abort();
  }, []);
  useEffect(() => {
    if (!selected) return;
    const c = new AbortController();
    void watchApi<WatchDetail>(`/${selected}`, "GET", undefined, c.signal)
      .then(setDetail)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => c.abort();
  }, [selected]);
  const refreshQuotes = useCallback(async () => {
    if (!selected || quoteLock.current || document.hidden) return;
    const id = selected;
    quoteLock.current = true;
    setRefreshing(true);
    try {
      const r = await watchApi<{ quotes: WatchQuote[]; error: string | null }>(
        `/${id}/quotes`,
      );
      if (scope.current !== id) return;
      setQuoteError(r.error || "");
      setQuotes(
        Object.fromEntries(
          r.quotes.map((q) => [q.instrument.instrument_id, q]),
        ),
      );
    } catch (e) {
      if (scope.current === id) {
        setQuoteError((e as Error).message);
        setQuotes({});
      }
    } finally {
      quoteLock.current = false;
      setRefreshing(false);
    }
  }, [selected]);
  useEffect(() => {
    if (!current || current.archived) return;
    const timer = setTimeout(() => void refreshQuotes(), 0);
    return () => clearTimeout(timer);
  }, [current, refreshQuotes]);
  useEffect(() => {
    if (!auto) return;
    const timer = window.setInterval(
      () => void refreshQuotes(),
      interval * 1000,
    );
    return () => clearInterval(timer);
  }, [auto, interval, refreshQuotes]);
  useEffect(() => {
    if (!selected || !instrumentId) return;
    let active = true;
    void loadChart(selected, instrumentId, period)
      .then((value) => {
        if (active) setChart(value);
      })
      .catch(() => {
        if (active)
          setChart({
            provider: "dhan",
            bars: [],
            error: "Chart unavailable. Please retry later.",
          });
      });
    return () => {
      active = false;
    };
  }, [selected, instrumentId, period, loadChart]);
  useEffect(() => {
    if (modal !== "add" || !search.trim()) return;
    const c = new AbortController();
    const timer = setTimeout(() => {
      void watchApi<WatchItem[]>(
        `/instruments?q=${encodeURIComponent(search)}&instrument_type=${searchKind}`,
        "GET",
        undefined,
        c.signal,
      )
        .then(setResults)
        .catch((e) => {
          if (e.name !== "AbortError") setError(e.message);
        });
    }, 300);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [search, searchKind, modal]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timer);
  }, [notice]);
  async function act(work: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function selectList(id: string) {
    if (id === selected) return;
    setSelected(id);
    setDetail(null);
    setChecked([]);
    setInstrumentId("");
    setChart(null);
    setQuotes({});
    setPage(1);
    setQuery("");
    setType("ALL");
    setError("");
    setImportResult(null);
  }
  function inspect(i: WatchItem) {
    if (i.instrument.instrument_id !== instrumentId) setChart(null);
    setInstrumentId(i.instrument.instrument_id);
    setTab("Overview");
    if (window.innerWidth < 1200) setMobilePanel(true);
  }
  async function reload() {
    await refreshLists();
    if (selected) await refreshDetail(selected);
  }
  async function saveList() {
    await act(async () => {
      if (modal === "create") {
        const row = await watchApi<Watchlist>("", "POST", {
          name,
          description,
        });
        await refreshLists();
        selectList(row.id);
      } else {
        await watchApi(`/${selected}`, "PATCH", { name, description });
        await reload();
      }
      setModal(null);
    });
  }
  async function patch(body: unknown) {
    await act(async () => {
      await watchApi(`/${selected}`, "PATCH", body);
      await reload();
      setModal(null);
    });
  }
  async function remove(ids: string[]) {
    await act(async () => {
      await watchApi(`/${selected}/remove`, "POST", { instrument_ids: ids });
      setChecked([]);
      if (ids.includes(instrumentId)) setInstrumentId("");
      await reload();
    });
  }
  async function trade(i: WatchItem, side: Side) {
    await act(async () => {
      if (!account)
        throw new Error("Select an eligible connected broker before trading.");
      if (i.kind === "INDEX")
        throw new Error(
          "Indices cannot be traded directly. Add an exact future or option contract.",
        );
      const match = await watchApi<Instrument>(
        `/${selected}/items/${i.instrument.instrument_id}/broker-instrument?account_id=${account.id}`,
      );
      if (!canOrder(match))
        throw new Error("This broker contract is not currently tradable.");
      setTicket({ account, instrument: match, side, quantity, orderType });
    });
  }
  function exportCsv() {
    void act(async () => {
      const response = await fetch(`/api/v1/watchlists/${selected}/export`, {
        cache: "no-store",
      });
      if (!response.ok) throw new Error("Export unavailable.");
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "watchlist.csv";
      a.click();
      URL.revokeObjectURL(url);
    });
  }
  const filtered = (current?.items || [])
    .filter(
      (i) =>
        (type === "ALL" || i.kind === type) &&
        i.instrument.symbol.toLowerCase().includes(query.toLowerCase()) &&
        (!minimum ||
          (quotes[i.instrument.instrument_id] &&
            Number(quotes[i.instrument.instrument_id].last_price) >=
              Number(minimum))) &&
        (!positive ||
          (change(
            quotes[i.instrument.instrument_id],
            history[i.instrument.instrument_id],
          ) ?? -1) > 0) &&
        (!minVolume ||
          Number(quotes[i.instrument.instrument_id]?.volume) >=
            Number(minVolume)),
    )
    .sort((a, b) =>
      group === "type"
        ? a.kind.localeCompare(b.kind) || a.ordering - b.ordering
        : a.ordering - b.ordering,
    );
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const actualPage = Math.min(page, pages);
  const rows = filtered.slice(
    (actualPage - 1) * pageSize,
    actualPage * pageSize,
  );
  const visibleRowIds = rows
    .map((row) => row.instrument.instrument_id)
    .join(",");
  useEffect(() => {
    if (!selected || !visibleRowIds) return;
    let active = true;
    // Visible page only, serial cold loads. Detail selection joins the same
    // in-flight request and cache rather than fetching row history a second time.
    void (async () => {
      for (const id of visibleRowIds.split(",")) {
        if (!active) break;
        try {
          const value = await loadChart(selected, id, "1M");
          if (!active) break;
          setHistory((previous) => ({
            ...previous,
            [id]: value.bars.slice(-22),
          }));
          setMetrics((previous) => {
            const next = { ...previous };
            if (value.metrics) next[id] = value.metrics;
            else delete next[id];
            return next;
          });
          if (value.error === "RATE_LIMITED" || value.error === "AUTH_REQUIRED")
            break;
        } catch {
          /* A failed row stays unavailable; other visible rows can load. */
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [selected, visibleRowIds, loadChart]);
  const tableColSpan = 4 + visible.length;
  const periodResult = periodChange(
    period,
    quote,
    chart,
    history[instrumentId],
  );
  const panel = item ? (
    <>
      <header className="wl-instrument-heading">
        <div>
          <strong>{item.instrument.symbol}</strong>
          <small>
            {item.instrument.exchange} · {badge[item.kind]}
          </small>
        </div>
        <span className="wl-badge">{badge[item.kind]}</span>
      </header>
      <div className="wl-price" title="Change across selected chart period">
        {numberText(quote?.last_price)}{" "}
        <small
          className={
            periodResult.value == null
              ? "neutral"
              : periodResult.value! > 0
                ? "up"
                : periodResult.value! < 0
                  ? "down"
                  : "neutral"
          }
        >
          {period} {changeText(periodResult.value)}
        </small>
      </div>
      <div className="wl-tabs" role="tablist" aria-label="Instrument views">
        {["Overview", "Option Chain", "News"].map((t, index, tabs) => (
          <button
            key={t}
            role="tab"
            id={`${panelId}-${index}`}
            aria-controls={`${panelId}-content`}
            aria-selected={tab === t}
            tabIndex={tab === t ? 0 : -1}
            onClick={() => setTab(t)}
            onKeyDown={(event) => {
              const next =
                event.key === "ArrowRight"
                  ? (index + 1) % tabs.length
                  : event.key === "ArrowLeft"
                    ? (index + tabs.length - 1) % tabs.length
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? tabs.length - 1
                        : null;
              if (next == null) return;
              event.preventDefault();
              setTab(tabs[next]);
              document.getElementById(`${panelId}-${next}`)?.focus();
            }}
          >
            {t}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${panelId}-content`}
        aria-labelledby={`${panelId}-${["Overview", "Option Chain", "News"].indexOf(tab)}`}
        tabIndex={0}
      >
        {tab === "Option Chain" ? (
          <p className="wl-empty">Option chain coming later</p>
        ) : tab === "News" ? (
          <NewsPanel
            listId={selected}
            instrumentId={instrumentId}
            symbol={item.instrument.symbol}
          />
        ) : (
          <>
            {chart ? (
              <MarketChart bars={chart.bars} />
            ) : (
              <p role="status" className="wl-empty">
                Loading chart…
              </p>
            )}
            <div className="wl-periods">
              {["1D", "1W", "1M", "3M", "1Y"].map((p) => (
                <button
                  key={p}
                  aria-pressed={period === p}
                  onClick={() => {
                    if (p === period) return;
                    setChart(null);
                    setPeriod(p);
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
            {tab === "Overview" && (
              <section aria-label="Price / market data">
                <h3>Price / market data</h3>
                <dl className="wl-metrics">
                  {[
                    ["Open", quote?.open],
                    ["Prev Close", previousClose(quote, history[instrumentId])],
                    ["High", quote?.high],
                    ["Low", quote?.low],
                    ["Volume", quote?.volume],
                    [
                      "Avg. volume (20d)",
                      metrics[instrumentId]?.average_volume20,
                    ],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>
                        {k === "Volume" || k === "Avg. volume (20d)"
                          ? indianVolume(v)
                          : numberText(v)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            )}
            <ReferencePanel
              listId={selected}
              instrumentId={instrumentId}
              marketDetails={
                <>
                  <p>Market data · Dhan · quote / OHLCV snapshot</p>
                  <p>
                    Source time ·{" "}
                    {quote?.provider_source_time
                      ? time(quote.provider_source_time)
                      : "Unavailable"}
                    <br />
                    Received · {quote ? time(quote.received_at) : "Unavailable"}
                    <br />
                    Freshness · Snapshot; not continuously streaming
                  </p>
                  <p>
                    Chart ·{" "}
                    {chart?.error
                      ? "Unavailable"
                      : chart
                        ? `${chart.interval} completed bars`
                        : "Loading"}
                  </p>
                  <small className="wl-source" aria-label="Period change basis">
                    {periodResult.basis}
                    <br />
                    {periodResult.startTime
                      ? sessionDate(periodResult.startTime)
                      : period === "1D"
                        ? "Previous session"
                        : "Unavailable"}{" "}
                    {numberText(periodResult.start)} →{" "}
                    {periodResult.endTime
                      ? sessionDate(periodResult.endTime)
                      : "Unavailable"}{" "}
                    {numberText(periodResult.end)}
                  </small>
                </>
              }
            />
          </>
        )}
      </div>
      <section className="wl-quick">
        <h3>Quick Trade {account ? `(${account.name})` : ""}</h3>
        <label>
          Broker
          <select
            aria-label="Execution broker"
            value={brokerId}
            onChange={(e) => setBrokerId(e.target.value)}
          >
            <option value="">Select connected broker</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} · {a.provider}
              </option>
            ))}
          </select>
        </label>
        <div className="wl-tabs">
          {(["EQUITY", "OPTION", "FUTURE"] as Kind[]).map((k) => (
            <button
              key={k}
              aria-pressed={item.kind === k}
              disabled={item.kind !== k}
            >
              {label[k]}
            </button>
          ))}
        </div>
        <div className="wl-two">
          <label>
            {item.kind === "EQUITY" ? "Quantity" : "Lots"}
            <input
              type="number"
              min="1"
              max="100000"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
            />
          </label>
          <label>
            Order type
            <select
              value={orderType}
              onChange={(e) => setOrderType(e.target.value)}
            >
              <option>LIMIT</option>
              <option>MARKET</option>
            </select>
          </label>
        </div>
        <div className="wl-two">
          <button
            className="wl-buy"
            disabled={!account || busy || item.kind === "INDEX" || quantity < 1}
            onClick={() => void trade(item, "BUY")}
          >
            Buy
          </button>
          <button
            className="wl-sell"
            disabled={!account || busy || item.kind === "INDEX" || quantity < 1}
            onClick={() => void trade(item, "SELL")}
          >
            Sell
          </button>
        </div>
        <small>
          Opens the broker ticket. Preview and confirmation are required.
        </small>
        {!accounts.length && (
          <Link href="/brokers">Connect a trading-enabled broker</Link>
        )}
        {item.kind === "INDEX" && (
          <p>
            Indices are reference instruments and cannot be ordered directly.
          </p>
        )}
      </section>
    </>
  ) : (
    <div className="wl-empty">
      Select a symbol to view its chart and broker actions.
    </div>
  );
  return (
    <section className="watchlists-workspace">
      <header className="wl-page-head">
        <div>
          <h1>Watchlists</h1>
          <p>
            Track opportunities, analyze in real-time, and trade directly from
            your watchlists.
          </p>
        </div>
        <div className="wl-actions">
          <button
            disabled={!current || current.archived}
            onClick={() => {
              setCsv("");
              setImportResult(null);
              setModal("import");
            }}
          >
            ↥ Import
          </button>
          <button disabled={!current} onClick={exportCsv}>
            ↥ Export (CSV)
          </button>
          <button
            className="wl-primary"
            onClick={() => {
              setName("");
              setDescription("");
              setModal("create");
            }}
          >
            ＋ New Watchlist
          </button>
        </div>
      </header>
      {error && (
        <div role="alert" className="wl-error">
          {error}
          <button onClick={() => setError("")} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}
      {notice && (
        <div role="status" className="wl-toast">
          {notice}
        </div>
      )}
      <div className="wl-layout">
        <aside className="wl-navigator wl-card">
          <h2>My Watchlists</h2>
          <input
            aria-label="Search watchlists"
            placeholder="Search watchlists…"
            value={listSearch}
            onChange={(e) => setListSearch(e.target.value)}
          />
          <nav aria-label="My watchlists">
            {lists
              .filter(
                (l) =>
                  l.archived === trash &&
                  l.name.toLowerCase().includes(listSearch.toLowerCase()),
              )
              .map((l) => (
                <button
                  key={l.id}
                  className={l.id === selected ? "selected" : ""}
                  aria-current={l.id === selected ? "true" : undefined}
                  onClick={() => selectList(l.id)}
                >
                  <span>
                    <strong>
                      {l.favorite ? "★ " : ""}
                      {l.name}
                    </strong>
                    <small>{l.count} symbols</small>
                  </span>
                  <span aria-hidden="true">›</span>
                </button>
              ))}
          </nav>
          <button
            className="wl-trash"
            aria-pressed={trash}
            onClick={() => setTrash(!trash)}
          >
            {trash ? "← Active watchlists" : "♧ Trash"}
          </button>
          {!loaded && <p role="status">Loading watchlists…</p>}
        </aside>
        <div className="wl-main wl-card">
          {!current ? (
            <div className="wl-empty">
              <h2>
                {selected ? "Loading watchlist…" : "Your market, organized"}
              </h2>
              <p>
                Create a watchlist and add exact instruments to start tracking.
              </p>
            </div>
          ) : (
            <>
              <header className="wl-detail-head">
                <button
                  className="wl-star"
                  aria-label={
                    current.favorite ? "Unpin watchlist" : "Pin watchlist"
                  }
                  onClick={() => void patch({ favorite: !current.favorite })}
                >
                  {current.favorite ? "★" : "☆"}
                </button>
                <div>
                  <h2>
                    {current.name}{" "}
                    <button
                      aria-label="Edit watchlist"
                      onClick={() => {
                        setName(current.name);
                        setDescription(current.description);
                        setModal("edit");
                      }}
                    >
                      ✎
                    </button>
                  </h2>
                  <p>
                    {current.description ||
                      "Your personal instrument collection."}
                  </p>
                </div>
                <small>
                  Last updated
                  <br />
                  {time(current.updated_at)}
                </small>
                <label className="wl-auto">
                  <input
                    type="checkbox"
                    checked={auto}
                    onChange={(e) => setAuto(e.target.checked)}
                    disabled={current.archived}
                  />{" "}
                  Auto-refresh
                </label>
                <select
                  aria-label="Refresh interval"
                  value={interval}
                  onChange={(e) => setIntervalValue(Number(e.target.value))}
                >
                  {[15, 30, 60].map((n) => (
                    <option key={n} value={n}>
                      {n}s
                    </option>
                  ))}
                </select>
                <button
                  aria-label="Refresh quotes"
                  disabled={refreshing || current.archived}
                  onClick={() => void refreshQuotes()}
                >
                  ↻
                </button>
                <details key={String(current.archived)}>
                  <summary aria-label="Watchlist actions">•••</summary>
                  <button
                    onClick={() =>
                      current.archived
                        ? void patch({ archived: false })
                        : setModal("archive")
                    }
                  >
                    {current.archived ? "Restore watchlist" : "Move to Trash"}
                  </button>
                </details>
              </header>
              <div className="wl-tabs wl-types">
                {kinds.map((k) => (
                  <button
                    key={k}
                    aria-pressed={type === k}
                    onClick={() => {
                      setType(k);
                      setPage(1);
                    }}
                  >
                    {label[k]}{" "}
                    {current.items.filter((i) => i.kind === k).length}
                  </button>
                ))}
                <button
                  aria-pressed={type === "ALL"}
                  onClick={() => setType("ALL")}
                >
                  All {current.items.length}
                </button>
              </div>
              <div className="wl-tools">
                <input
                  aria-label="Search symbols in this list"
                  placeholder="Search symbols in this list…"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setPage(1);
                  }}
                />
                <details>
                  <summary>Filters</summary>
                  <div className="wl-popover">
                    <label>
                      Minimum LTP
                      <input
                        type="number"
                        min="0"
                        value={minimum}
                        onChange={(e) => setMinimum(e.target.value)}
                      />
                    </label>
                    <label>
                      Minimum volume
                      <input
                        type="number"
                        min="0"
                        value={minVolume}
                        onChange={(e) => setMinVolume(e.target.value)}
                      />
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={positive}
                        onChange={(e) => setPositive(e.target.checked)}
                      />{" "}
                      Positive change only
                    </label>
                  </div>
                </details>
                <details>
                  <summary>Columns</summary>
                  <div className="wl-popover">
                    {columns.map((c) => (
                      <label key={c}>
                        <input
                          type="checkbox"
                          checked={visible.includes(c)}
                          onChange={() =>
                            setVisible((v) =>
                              v.includes(c)
                                ? v.filter((x) => x !== c)
                                : [...v, c],
                            )
                          }
                        />
                        {c}
                      </label>
                    ))}
                  </div>
                </details>
                <label>
                  Group by
                  <select
                    value={group}
                    onChange={(e) => setGroup(e.target.value)}
                  >
                    <option value="none">None</option>
                    <option value="type">Type</option>
                  </select>
                </label>
              </div>
              {quoteError && (
                <p className="wl-data-notice" role="status">
                  Dhan quotes unavailable. Instruments are preserved.{" "}
                  {quoteError.replaceAll("_", " ")}
                </p>
              )}
              {checked.length > 0 && (
                <div className="wl-bulk">
                  <span>{checked.length} selected</span>
                  <button
                    disabled={busy || current.archived}
                    onClick={() => void remove(checked)}
                  >
                    Remove selected
                  </button>
                  <select
                    aria-label="Target watchlist"
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                  >
                    <option value="">Choose destination</option>
                    {lists
                      .filter((l) => !l.archived && l.id !== selected)
                      .map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name}
                        </option>
                      ))}
                  </select>
                  {["Copy", "Move"].map((action) => (
                    <button
                      key={action}
                      disabled={!target || busy || current.archived}
                      onClick={() =>
                        void act(async () => {
                          await watchApi(`/${selected}/transfer`, "POST", {
                            target_id: target,
                            instrument_ids: checked,
                            move: action === "Move",
                          });
                          setChecked([]);
                          await reload();
                        })
                      }
                    >
                      {action}
                    </button>
                  ))}
                </div>
              )}
              <div className="wl-table-wrap">
                <table className="wl-table">
                  <thead>
                    <tr>
                      <th>
                        <input
                          type="checkbox"
                          aria-label="Select current page"
                          checked={
                            rows.length > 0 &&
                            rows.every((i) =>
                              checked.includes(i.instrument.instrument_id),
                            )
                          }
                          onChange={(e) =>
                            setChecked(
                              e.target.checked
                                ? rows.map((i) => i.instrument.instrument_id)
                                : [],
                            )
                          }
                        />
                      </th>
                      <th>Symbol</th>
                      <th>Type</th>
                      {columns
                        .filter((c) => visible.includes(c))
                        .map((c) => (
                          <th
                            key={c}
                            title={
                              c === "1D %"
                                ? "Change from previous trading session close"
                                : c === "Quick Chart (1M)"
                                  ? "Last ~1 month of completed daily closes"
                                  : undefined
                            }
                          >
                            {c}
                          </th>
                        ))}
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((i) => {
                      const id = i.instrument.instrument_id,
                        q = quotes[id],
                        delta = change(q, history[id]);
                      return (
                        <tr
                          key={id}
                          className={
                            instrumentId === id ? "wl-row-selected" : ""
                          }
                        >
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`Select ${i.instrument.symbol}`}
                              checked={checked.includes(id)}
                              onChange={(e) =>
                                setChecked((old) =>
                                  e.target.checked
                                    ? [...old, id]
                                    : old.filter((v) => v !== id),
                                )
                              }
                            />
                          </td>
                          <td>
                            <button
                              className="wl-symbol"
                              onClick={() => inspect(i)}
                            >
                              {i.instrument.symbol}
                            </button>
                            <small>
                              {i.instrument.exchange}
                              {i.instrument.expiry
                                ? ` · ${i.instrument.expiry.slice(0, 10)}`
                                : ""}
                            </small>
                          </td>
                          <td>
                            <span
                              className={`wl-badge ${i.kind.toLowerCase()}`}
                            >
                              {badge[i.kind]}
                            </span>
                          </td>
                          {visible.includes("LTP") && (
                            <td>{numberText(q?.last_price)}</td>
                          )}
                          {visible.includes("1D %") && (
                            <td
                              className={
                                delta == null || delta === 0
                                  ? "neutral"
                                  : delta > 0
                                    ? "up"
                                    : "down"
                              }
                            >
                              {changeText(delta)}
                            </td>
                          )}
                          {visible.includes("Volume") && (
                            <td>{numberText(q?.volume)}</td>
                          )}
                          {visible.includes("RSI (14)") && (
                            <td
                              title={
                                metrics[i.instrument.instrument_id]
                                  ? `${metrics[i.instrument.instrument_id].basis} · ${metrics[i.instrument.instrument_id].as_of}`
                                  : "Daily indicator history is loading or unavailable"
                              }
                            >
                              {numberText(
                                metrics[i.instrument.instrument_id]?.rsi14,
                              )}
                            </td>
                          )}
                          {visible.includes("Trend") && (
                            <td
                              title={
                                metrics[i.instrument.instrument_id]
                                  ? `${metrics[i.instrument.instrument_id].basis} · ${metrics[i.instrument.instrument_id].as_of}`
                                  : "Daily trend history is loading or unavailable"
                              }
                            >
                              {metrics[i.instrument.instrument_id]?.trend ||
                                "—"}
                            </td>
                          )}
                          {visible.includes("Quick Chart (1M)") && (
                            <td>
                              <MarketChart bars={history[id] || []} compact />
                            </td>
                          )}
                          <td>
                            <div className="wl-row-actions">
                              <button
                                aria-label={`View ${i.instrument.symbol} chart`}
                                onClick={() => inspect(i)}
                              >
                                ↗
                              </button>
                              <button
                                className="wl-buy"
                                aria-label={`Buy ${i.instrument.symbol}`}
                                disabled={
                                  busy ||
                                  !account ||
                                  i.kind === "INDEX" ||
                                  current.archived
                                }
                                onClick={() => void trade(i, "BUY")}
                              >
                                B
                              </button>
                              <button
                                className="wl-sell"
                                aria-label={`Sell ${i.instrument.symbol}`}
                                disabled={
                                  busy ||
                                  !account ||
                                  i.kind === "INDEX" ||
                                  current.archived
                                }
                                onClick={() => void trade(i, "SELL")}
                              >
                                S
                              </button>
                              <details>
                                <summary
                                  aria-label={`${i.instrument.symbol} actions`}
                                >
                                  ⋮
                                </summary>
                                <button
                                  disabled={busy || current.archived}
                                  onClick={() => void remove([id])}
                                >
                                  Remove {i.instrument.symbol}
                                </button>
                              </details>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                    {!rows.length && (
                      <tr>
                        <td colSpan={tableColSpan} className="wl-empty">
                          {current.items.length
                            ? "No symbols match your filters."
                            : "This watchlist is empty. Add symbols to begin."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <footer className="wl-pagination">
                <span>
                  Showing{" "}
                  {filtered.length ? (actualPage - 1) * pageSize + 1 : 0}–
                  {Math.min(actualPage * pageSize, filtered.length)} of{" "}
                  {filtered.length} symbols
                </span>
                <button
                  aria-label="Previous page"
                  disabled={actualPage === 1}
                  onClick={() => setPage(actualPage - 1)}
                >
                  ‹
                </button>
                <span>
                  {actualPage} / {pages}
                </span>
                <button
                  aria-label="Next page"
                  disabled={actualPage === pages}
                  onClick={() => setPage(actualPage + 1)}
                >
                  ›
                </button>
                <label>
                  Rows per page
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setPage(1);
                    }}
                  >
                    {[10, 25, 50].map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </label>
              </footer>
              <button
                className="wl-add"
                disabled={current.archived}
                onClick={() => {
                  setSearch("");
                  setResults([]);
                  setModal("add");
                }}
              >
                ＋ Add Symbols
              </button>
              <small className="wl-source">
                Quick Chart (1M): last ~1 month of completed daily closes · —
                means unavailable
              </small>
            </>
          )}
        </div>
        <aside
          className="wl-inspector wl-card"
          aria-label="Selected instrument"
        >
          {!mobilePanel && panel}
        </aside>
      </div>
      {current && (
        <div className="wl-bottom">
          <section className="wl-card">
            <h2>Recent Activity</h2>
            {current.activity.length ? (
              current.activity.map((a) => (
                <div className="wl-activity" key={a.id}>
                  <strong>{a.action}</strong>
                  <span>{a.symbol || current.name}</span>
                  <time>{time(a.created_at)}</time>
                </div>
              ))
            ) : (
              <p>No activity yet.</p>
            )}
          </section>
          <section className="wl-card">
            <h2>Notes</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void act(async () => {
                  await watchApi(`/${selected}/notes`, "POST", { text: note });
                  setNote("");
                  await refreshDetail(selected);
                });
              }}
            >
              <input
                aria-label="Watchlist note"
                placeholder="Add a note…"
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <button disabled={!note.trim() || busy || current.archived}>
                Save
              </button>
            </form>
            {current.notes.map((n) => (
              <div key={n.id} className="wl-note">
                <time>{time(n.created_at)}</time>
                <p>{n.text}</p>
              </div>
            ))}
          </section>
        </div>
      )}
      {(modal === "create" || modal === "edit") && (
        <WatchDialog
          title={modal === "create" ? "New Watchlist" : "Edit Watchlist"}
          close={() => setModal(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void saveList();
            }}
          >
            <label>
              Name
              <input
                autoFocus
                required
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Description
              <input
                maxLength={240}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <button className="wl-primary" disabled={busy || !name.trim()}>
              Save watchlist
            </button>
            {error && <p role="alert">{error}</p>}
          </form>
        </WatchDialog>
      )}
      {modal === "archive" && (
        <WatchDialog
          title="Move watchlist to Trash?"
          close={() => setModal(null)}
        >
          <p>
            Your symbols and notes will be retained. You can restore this
            watchlist from Trash.
          </p>
          <button
            disabled={busy}
            onClick={() => void patch({ archived: true })}
          >
            Move to Trash
          </button>
        </WatchDialog>
      )}
      {modal === "add" && (
        <WatchDialog title="Add Symbols" close={() => setModal(null)}>
          <label>
            Instrument type
            <select
              value={searchKind}
              onChange={(e) => {
                setResults([]);
                setSearchKind(e.target.value as Kind);
              }}
            >
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {label[k]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Search instruments
            <input
              autoFocus
              value={search}
              maxLength={80}
              placeholder="Search the Dhan catalog…"
              onChange={(e) => {
                setSearch(e.target.value);
                setResults([]);
              }}
            />
          </label>
          <div className="wl-search-results">
            {results.map((i) => (
              <div key={i.instrument.instrument_id}>
                <span>
                  <strong>{i.instrument.symbol}</strong>
                  <small>
                    {i.instrument.exchange} · {badge[i.kind]} ·{" "}
                    {i.instrument.native.native_id}
                    {i.instrument.expiry
                      ? ` · ${i.instrument.expiry.slice(0, 10)}`
                      : ""}
                  </small>
                </span>
                <button
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      const r = await watchApi<{
                        added: number;
                        duplicates: number;
                      }>(`/${selected}/items`, "POST", {
                        instrument_ids: [i.instrument.instrument_id],
                      });
                      await reload();
                      setNotice(
                        r.added
                          ? `${i.instrument.symbol} added.`
                          : "Already in this watchlist.",
                      );
                    })
                  }
                >
                  Add {i.instrument.symbol}
                </button>
              </div>
            ))}
            {search && !results.length && (
              <p>No results yet. Search an exact symbol or contract.</p>
            )}
          </div>
          {error && <p role="alert">{error}</p>}
        </WatchDialog>
      )}
      {modal === "import" && (
        <WatchDialog title="Import CSV" close={() => setModal(null)}>
          <p>
            Up to 100 rows. Required column: canonical_symbol (e.g.
            NSE:RELIANCE). Instruments must resolve uniquely.
          </p>
          <input
            aria-label="CSV file"
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                if (file.size > 32768) {
                  setError("CSV is limited to 32 KB.");
                  return;
                }
                void file.text().then(setCsv);
              }
            }}
          />
          <label>
            CSV content
            <textarea
              value={csv}
              onChange={(e) => setCsv(e.target.value)}
              maxLength={32768}
              placeholder={"canonical_symbol\nNSE:RELIANCE"}
            />
          </label>
          <button
            className="wl-primary"
            disabled={!csv || busy}
            onClick={() =>
              void act(async () => {
                setImportResult(
                  await watchApi(`/${selected}/import`, "POST", { csv }),
                );
                await reload();
              })
            }
          >
            Import symbols
          </button>
          {importResult && (
            <div role="status">
              <p>
                Added {importResult.added} · Duplicates{" "}
                {importResult.duplicates} · Unresolved{" "}
                {importResult.invalid.length}
              </p>
              {importResult.invalid.map((i) => (
                <p key={i.row}>
                  Row {i.row}: {i.symbol} — {i.reason.replaceAll("_", " ")}
                </p>
              ))}
            </div>
          )}
          {error && <p role="alert">{error}</p>}
        </WatchDialog>
      )}
      {mobilePanel && item && (
        <WatchDialog
          title={`${item.instrument.symbol} details`}
          close={() => setMobilePanel(false)}
        >
          {panel}
        </WatchDialog>
      )}
      {ticket && (
        <OrderTicket
          account={ticket.account}
          initial={ticket}
          close={() => setTicket(null)}
        />
      )}
    </section>
  );
}
type WatchNewsClaim = {
  kind: string;
  subject: string;
  scope: string;
  values: Record<string, unknown>;
  provider: string;
  provider_tool: string;
  source_time: string | null;
  received_at: string;
  freshness: string;
};
type WatchNewsBatch = {
  claims: WatchNewsClaim[];
  state: string;
  failures?: string[];
};

export function NewsPanel({
  listId,
  instrumentId,
  symbol,
}: {
  listId: string;
  instrumentId: string;
  symbol: string;
}) {
  const requestKey = `${listId}:${instrumentId}:${symbol}`;
  const [loadedResult, setLoadedResult] = useState<{
    key: string;
    result: WatchNewsBatch;
  } | null>(null);
  const result = loadedResult?.key === requestKey ? loadedResult.result : null;
  useEffect(() => {
    const c = new AbortController();
    void watchApi<WatchNewsBatch>(
      `/${listId}/items/${instrumentId}/news`,
      "GET",
      undefined,
      c.signal,
    )
      .then((value) => setLoadedResult({ key: requestKey, result: value }))
      .catch(() => {
        if (!c.signal.aborted)
          setLoadedResult({
            key: requestKey,
            result: { claims: [], state: "UNAVAILABLE", failures: [] },
          });
      });
    return () => c.abort();
  }, [listId, instrumentId, requestKey, symbol]);
  const claims = result?.claims || [];
  const symbolClaims = claims.filter(
    (claim) =>
      claim.scope.toUpperCase() === "INSTRUMENT" &&
      claim.subject.toUpperCase() === symbol.toUpperCase(),
  );
  const hasHeadline = (claim: WatchNewsClaim) =>
    typeof claim.values.latest_headline === "string" &&
    Boolean(claim.values.latest_headline.trim());
  const symbolStories = symbolClaims.filter(
    (claim) => claim.kind === "NEWS_SENTIMENT" && hasHeadline(claim),
  );
  const corporateEvents = symbolClaims.filter(
    (claim) =>
      claim.kind === "CORPORATE_EVENT" &&
      typeof claim.values.event_type === "string" &&
      Boolean(claim.values.event_type.trim()),
  );
  const eventsFailed = Boolean(
    result?.failures?.some((failure) =>
      failure.startsWith("get_stock_events:"),
    ),
  );
  const sectorClaims = claims.filter(
    (claim) => claim.scope.toUpperCase() === "SECTOR" && hasHeadline(claim),
  );
  const marketClaims = claims.filter(
    (claim) => claim.scope.toUpperCase() === "MARKET" && hasHeadline(claim),
  );
  const unavailable =
    result?.state === "AUTH_REQUIRED"
      ? "TapTide authorization is required."
      : result?.state === "RATE_LIMITED"
        ? "TapTide is rate limited. Try again later."
        : result?.state === "UNAVAILABLE" || result?.state === "PROVIDER_ERROR"
          ? "TapTide news is unavailable."
          : null;
  const story = (claim: WatchNewsClaim) => {
    const headline = claim.values.latest_headline;
    const eventType = claim.values.event_type;
    const eventDate = claim.values.event_date;
    return typeof headline === "string"
      ? headline
      : typeof eventType === "string"
        ? `${eventType}${typeof eventDate === "string" ? ` · ${eventDate}` : ""}`
        : "No headline details are available in the normalized result.";
  };
  const cards = (selected: WatchNewsClaim[], category: string) =>
    selected.map((claim, index) => (
      <article key={`${claim.provider_tool}-${claim.subject}-${index}`}>
        <strong>
          {claim.subject === "INDIA_MARKET" ? "India market" : claim.subject}
        </strong>
        <p>{story(claim)}</p>
        <small>
          {claim.provider === "tapetide" ? "TapTide" : claim.provider} ·{" "}
          {category} · {claim.scope.toLowerCase()} ·{" "}
          {claim.provider_tool.replaceAll("_", " ")} · Source time{" "}
          {claim.source_time ? time(claim.source_time) : "unavailable"} ·
          Received {time(claim.received_at)} ·{" "}
          {claim.freshness.replaceAll("_", " ")}
        </small>
      </article>
    ));
  return (
    <section className="wl-news">
      <p>TapTide · {result?.state || "Loading…"}</p>
      <section aria-label={`${symbol} company and symbol news`}>
        <h3>Company news</h3>
        {!result ? (
          <p role="status">Loading {symbol} news…</p>
        ) : symbolStories.length ? (
          cards(symbolStories, "Company news")
        ) : unavailable ? (
          <p>Symbol-specific news is unavailable from TapTide.</p>
        ) : (
          <p>No recent {symbol}-specific news.</p>
        )}
      </section>
      <section aria-label="Corporate events">
        <h3>Corporate events</h3>
        {!result ? (
          <p>Loading corporate events…</p>
        ) : corporateEvents.length ? (
          cards(corporateEvents, "Corporate event")
        ) : eventsFailed || unavailable ? (
          <p>Corporate events are unavailable from TapTide.</p>
        ) : (
          <p>No recent {symbol}-specific corporate events available.</p>
        )}
      </section>
      {sectorClaims.length > 0 && (
        <section aria-label="Related sector context">
          <h3>Related sector context</h3>
          {cards(sectorClaims, "Sector")}
        </section>
      )}
      {marketClaims.length > 0 && (
        <section aria-label="Market-wide context">
          <h3>Market-wide context</h3>
          {cards(marketClaims, "Market-wide")}
        </section>
      )}
      {unavailable && <p role="status">{unavailable}</p>}
      {result?.state === "PARTIAL" && (
        <p role="status">Some TapTide news sources are unavailable.</p>
      )}
      {!result && <p role="status">Loading TapTide news…</p>}
    </section>
  );
}

export function ReferencePanel({
  listId,
  instrumentId,
  marketDetails,
}: {
  listId: string;
  instrumentId: string;
  marketDetails?: ReactNode;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const key = `${listId}:${instrumentId}`;
  const cache = useRef(
    new Map<string, { at: number; value: WatchReference }>(),
  );
  const [loaded, setLoaded] = useState<{
    key: string;
    value: WatchReference;
  } | null>(null);
  const value = loaded?.key === key ? loaded.value : null;
  useEffect(() => {
    let active = true;
    const cached = cache.current.get(key);
    const request =
      cached &&
      Date.now() - cached.at <
        (cached.value.state === "UNAVAILABLE" ? 60000 : 900000)
        ? Promise.resolve(cached.value)
        : watchApi<WatchReference>(
            `/${listId}/items/${instrumentId}/reference`,
          );
    void request
      .then((result) => {
        if (!active) return;
        cache.current.set(key, { at: Date.now(), value: result });
        if (cache.current.size > 50)
          cache.current.delete(cache.current.keys().next().value!);
        setLoaded({ key, value: result });
      })
      .catch(() => {
        if (active)
          setLoaded({
            key,
            value: {
              symbol: "",
              provider: "tapetide",
              tool: "get_stock_quote",
              state: "UNAVAILABLE",
              market_cap_inr: null,
              pe_ratio: null,
              high_52_week: null,
              low_52_week: null,
              received_at: new Date().toISOString(),
              source_time: null,
              freshness: "UNAVAILABLE",
            },
          });
      });
    return () => {
      active = false;
    };
  }, [key, listId, instrumentId]);
  return (
    <>
      <section aria-label="Reference / fundamentals" className="wl-reference">
        <h3>Reference / fundamentals</h3>
        {[
          {
            title: "Fundamentals",
            values: [
              ["Market Cap", indianMarketCap(value?.market_cap_inr)],
              ["PE", numberText(value?.pe_ratio)],
            ],
          },
          {
            title: "Price reference",
            values: [
              ["52W High", numberText(value?.high_52_week)],
              ["52W Low", numberText(value?.low_52_week)],
            ],
          },
        ].map((group) => (
          <div key={group.title}>
            <h4>{group.title}</h4>
            <dl className="wl-metrics">
              {group.values.map(([name, display]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd
                    title={
                      display === "—"
                        ? "Data unavailable from configured providers"
                        : undefined
                    }
                  >
                    {display}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </section>
      <details
        className="wl-data-details"
        open={detailsOpen}
        onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
      >
        <summary aria-expanded={detailsOpen}>Data details</summary>
        <div className="wl-source">
          {marketDetails}
          {value ? (
            <>
              <p>
                Reference data ·{" "}
                {value.provider === "tapetide" ? "TapTide" : value.provider}
                <br />
                Source / tool · {value.tool.replaceAll("_", " ")}
                <br />
                Source time ·{" "}
                {value.source_time ? time(value.source_time) : "Unavailable"}
                <br />
                Received · {time(value.received_at)}
                <br />
                Freshness · {value.freshness.replaceAll("_", " ")}
                <br />
                Availability · {value.state.replaceAll("_", " ")}
              </p>
              {value.state !== "AVAILABLE" && (
                <p>
                  Some reference values are unavailable from the configured
                  provider.
                </p>
              )}
              <p>
                Reference timestamps describe the provider snapshot, not
                individual filing dates.
              </p>
            </>
          ) : (
            <p>Loading reference data…</p>
          )}
        </div>
      </details>
    </>
  );
}
