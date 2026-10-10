"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { OrderTicket } from "../brokers/order-ticket";
import { brokerApi, type Account } from "../../lib/brokers";
import type { Capability, Side } from "../../lib/broker-orders";
import type {
  OptionChainSnapshot,
  OptionContractRequest,
  OptionLegSnapshot,
} from "../../lib/options";
import {
  chainApi,
  chainCompactNumber as compact,
  chainMessages,
  chainNumber as num,
  expiryLabel,
  retrievedLabel,
} from "../../lib/option-chain-client";

type Broker = { account: Account; capability: Capability };
const columns = ["OI", "ΔOI", "Volume", "IV %", "Bid", "Ask", "LTP"];
const fields = [
  "open_interest",
  "change_in_open_interest",
  "volume",
  "implied_volatility",
  "bid",
  "ask",
  "ltp",
] as const;

type ChainField = (typeof fields)[number];

function fieldValue(field: ChainField, value: string | null | undefined) {
  return ["open_interest", "change_in_open_interest", "volume"].includes(field)
    ? compact(value, field === "change_in_open_interest")
    : num(value);
}

function signedClass(value: string | null | undefined) {
  const parsed = Number(value);
  return parsed > 0
    ? "chain-value-positive"
    : parsed < 0
      ? "chain-value-negative"
      : "";
}

export function OptionsWorkspace() {
  const [search, setSearch] = useState("");
  const [choices, setChoices] = useState<string[]>([]);
  const [searching, setSearching] = useState(true);
  const [searchError, setSearchError] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [underlying, setUnderlying] = useState("");
  const [expiries, setExpiries] = useState<string[]>([]);
  const [expiry, setExpiry] = useState("");
  const [expiryBusy, setExpiryBusy] = useState(false);
  const [expiryError, setExpiryError] = useState("");
  const [windowSize, setWindowSize] = useState(10);
  const [refresh, setRefresh] = useState(0);
  const [expiryReload, setExpiryReload] = useState(0);
  const [snapshot, setSnapshot] = useState<{
    key: string;
    data: OptionChainSnapshot;
  } | null>(null);
  const [fetchState, setFetchState] = useState({
    key: "",
    error: "",
    done: false,
  });
  const [selection, setSelection] = useState("");
  const [mobileSide, setMobileSide] = useState<"ce" | "pe">("ce");
  const [brokers, setBrokers] = useState<Broker[]>([]);
  const [brokerId, setBrokerId] = useState("");
  const [brokersLoaded, setBrokersLoaded] = useState(false);
  const [ticket, setTicket] = useState<{
    account: Account;
    canonical: { contract: OptionContractRequest; side: Side };
  } | null>(null);
  const key = `${underlying}|${expiry}|${windowSize}`;
  const requestKey = `${key}|${refresh}`;
  const data = snapshot?.key === key ? snapshot.data : null;
  const busy = !!expiry && (fetchState.key !== requestKey || !fetchState.done);
  const error = fetchState.key === requestKey ? fetchState.error : "";
  const selected =
    data?.rows
      .flatMap((r) => [r.ce, r.pe])
      .find((leg) => leg?.contract.canonical_id === selection) || null;
  const broker = brokers.find((b) => b.account.id === brokerId);
  const firstLeg = data?.rows
    .flatMap((row) => [row.ce, row.pe])
    .find((leg): leg is OptionLegSnapshot => leg !== null);
  const providerLabel = data
    ? data.provenance.provider === "dhan"
      ? "Dhan"
      : data.provenance.provider
    : "";
  const currentLiveData =
    data?.provenance.provider === "dhan" &&
    data.provenance.freshness === "FRESH" &&
    !data.provenance.cached &&
    !error;

  useEffect(() => {
    const c = new AbortController();
    const timer = setTimeout(() => {
      setSearching(true);
      setSearchError("");
      void chainApi<string[]>(
        `underlyings?query=${encodeURIComponent(search)}&limit=50`,
        c.signal,
      )
        .then((items) => {
          if (!c.signal.aborted) setChoices(items);
        })
        .catch((e: Error) => {
          if (!c.signal.aborted) {
            setChoices([]);
            setSearchError(e.message);
          }
        })
        .finally(() => {
          if (!c.signal.aborted) setSearching(false);
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      c.abort();
    };
  }, [search]);
  useEffect(() => {
    if (!underlying) return;
    const c = new AbortController();
    void chainApi<string[]>(
      `expiries?underlying=${encodeURIComponent(underlying)}`,
      c.signal,
    )
      .then((items) => {
        if (c.signal.aborted) return;
        setExpiries(items);
        setExpiry(items[0] || "");
        if (!items.length) setExpiryError(chainMessages.no_option_contracts);
      })
      .catch((e: Error) => {
        if (!c.signal.aborted) setExpiryError(e.message);
      })
      .finally(() => {
        if (!c.signal.aborted) setExpiryBusy(false);
      });
    return () => c.abort();
  }, [underlying, expiryReload]);
  useEffect(() => {
    if (!underlying || !expiry) return;
    const c = new AbortController();
    const query = new URLSearchParams({
      underlying,
      expiry,
      around_atm: String(windowSize),
    });
    void chainApi<OptionChainSnapshot>(`chain?${query}`, c.signal)
      .then((next) => {
        if (c.signal.aborted) return;
        setSnapshot({ key, data: next });
        setFetchState({ key: requestKey, done: true, error: "" });
      })
      .catch((e: Error) => {
        if (!c.signal.aborted)
          setFetchState({ key: requestKey, done: true, error: e.message });
      });
    return () => c.abort();
  }, [underlying, expiry, windowSize, key, requestKey]);
  useEffect(() => {
    const c = new AbortController();
    void brokerApi<Account[]>("accounts", undefined, c.signal)
      .then(async (accounts) => {
        const capable = await Promise.all(
          accounts
            .filter((a) => a.state === "connected")
            .map(async (account) => {
              try {
                const capability = await brokerApi<Capability>(
                  `accounts/${account.id}/order-entry/capabilities`,
                  undefined,
                  c.signal,
                );
                return capability.enabled && capability.broker.supports_options
                  ? { account, capability }
                  : null;
              } catch {
                return null;
              }
            }),
        );
        if (c.signal.aborted) return;
        const valid = capable.filter((b): b is Broker => b !== null);
        setBrokers(valid);
        if (valid.length === 1) setBrokerId(valid[0].account.id);
      })
      .catch(() => {})
      .finally(() => {
        if (!c.signal.aborted) setBrokersLoaded(true);
      });
    return () => c.abort();
  }, []);

  function choose(value: string) {
    if (value === underlying) {
      setSearchOpen(false);
      return;
    }
    setUnderlying(value);
    setExpiry("");
    setExpiries([]);
    setExpiryError("");
    setExpiryBusy(true);
    setSelection("");
    setSearch(value);
    setSearchOpen(false);
  }
  function open(side: Side) {
    if (!selected || !broker || busy || error) return;
    const { exchange, underlying_symbol, expiry, strike, option_type } =
      selected.contract;
    setTicket({
      account: broker.account,
      canonical: {
        contract: { exchange, underlying_symbol, expiry, strike, option_type },
        side,
      },
    });
  }
  function legButton(leg: OptionLegSnapshot) {
    const c = leg.contract;
    return (
      <button
        className="chain-leg"
        aria-label={`Select ${c.underlying_symbol} ${c.strike} ${c.option_type}`}
        aria-pressed={selection === c.canonical_id}
        onClick={() => setSelection(c.canonical_id)}
      >
        <strong>{num(leg.market.ltp)}</strong>
        <small>
          {selection === c.canonical_id ? "Selected · " : ""}
          {leg.moneyness || "Moneyness unavailable"}
        </small>
      </button>
    );
  }
  function cells(leg: OptionLegSnapshot | null, side: "ce" | "pe") {
    const keys = side === "ce" ? [...fields] : [...fields].reverse();
    return keys.map((field) => {
      const value = leg?.market[field];
      const moneyClass = leg?.moneyness
        ? `chain-money-${leg.moneyness.toLowerCase()}`
        : "";
      const direction =
        field === "change_in_open_interest" ? signedClass(value) : "";
      return (
        <td
          key={field}
          className={`${moneyClass} ${direction}`.trim() || undefined}
          title={value == null ? undefined : num(value, 6)}
        >
          {field === "ltp" && leg ? legButton(leg) : fieldValue(field, value)}
        </td>
      );
    });
  }
  return (
    <section className="options-workspace" aria-labelledby="options-title">
      <header className="options-title">
        <div>
          <h1 id="options-title">Options Analytics</h1>
          <p>
            Analyze option chains, track liquidity and open interest, and trade
            directly through your broker.
          </p>
        </div>
        <div className="options-title-actions">
          {data && (
            <span
              className={`options-data-badge ${currentLiveData ? "is-live" : ""}`}
            >
              <span aria-hidden="true">●</span>{" "}
              {currentLiveData
                ? "Live Data (Dhan)"
                : data.provenance.cached
                  ? `${providerLabel} cached snapshot`
                  : `${providerLabel} snapshot`}
            </span>
          )}
          <Link href="/settings#integrations">Provider connections</Link>
        </div>
      </header>
      <div className="options-controls">
        <div
          className="chain-search"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) {
              setSearchOpen(false);
            }
          }}
        >
          <label htmlFor="chain-search">Underlying</label>
          <input
            id="chain-search"
            type="search"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={searchOpen}
            aria-controls={searchOpen ? "chain-suggestions" : undefined}
            autoComplete="off"
            value={search}
            placeholder="NIFTY, BANKNIFTY, HDFCBANK…"
            onFocus={() => setSearchOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSearchOpen(false);
            }}
            onChange={(e) => {
              setSearch(e.target.value);
              setSearching(true);
              setSearchOpen(true);
            }}
          />
          {searchOpen && (
            <div
              id="chain-suggestions"
              className="chain-suggestions"
              aria-label="Underlying search results"
              aria-busy={searching}
            >
              {searching ? (
                <span role="status">Searching underlyings…</span>
              ) : (
                choices.map((u) => (
                  <button
                    key={u}
                    aria-label={u}
                    aria-pressed={u === underlying}
                    onClick={() => choose(u)}
                  >
                    <strong>{u}</strong>
                    <small>Load listed expiries</small>
                  </button>
                ))
              )}
              {!searching && !searchError && !choices.length && (
                <span>No optionable underlyings found.</span>
              )}
            </div>
          )}
        </div>
        <label>
          Expiry
          <select
            aria-label="Expiry"
            value={expiry}
            disabled={!expiries.length || expiryBusy}
            onChange={(e) => {
              setExpiry(e.target.value);
              setSelection("");
            }}
          >
            <option value="">
              {expiryBusy ? "Loading expiries…" : "Select underlying first"}
            </option>
            {expiries.map((e) => (
              <option key={e} value={e}>
                {expiryLabel(e)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Strike window
          <select
            aria-label="Strike window"
            value={windowSize}
            onChange={(e) => setWindowSize(Number(e.target.value))}
          >
            {[5, 10, 15, 20].map((n) => (
              <option key={n} value={n}>
                ±{n} strikes
              </option>
            ))}
          </select>
        </label>
        <button
          className="chain-refresh"
          disabled={!underlying || busy || expiryBusy}
          onClick={() => {
            if (!expiry) setExpiryReload((n) => n + 1);
            else setRefresh((n) => n + 1);
          }}
        >
          <span aria-hidden="true">↻</span> {busy ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {(searchError || expiryError || error) && (
        <div className="chain-notice chain-error" role="alert">
          {error || expiryError || searchError}{" "}
          <Link href="/settings#integrations">Check provider settings</Link>
          {data && (
            <p>
              Showing the previously retrieved snapshot. Trading actions are
              paused until refresh succeeds.
            </p>
          )}
        </div>
      )}
      {busy && (
        <div
          role="status"
          aria-label={
            data
              ? "Updating chain snapshot"
              : "Loading listed contracts and market data"
          }
          className={
            data ? "chain-loading chain-loading-inline" : "chain-loading"
          }
        >
          {data ? (
            <span>Updating chain snapshot…</span>
          ) : (
            <>
              <span className="options-sr-only">
                Loading listed contracts and market data…
              </span>
              <div className="chain-skeleton-summary" aria-hidden="true" />
              <div className="chain-skeleton-body" aria-hidden="true">
                {Array.from({ length: 7 }, (_, index) => (
                  <span key={index} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
      {data ? (
        <>
          <dl className="chain-summary">
            {[
              ["Underlying", data.underlying],
              ["Spot ₹", num(data.spot)],
              ["Expiry", expiryLabel(data.expiry)],
              ["DTE", `${data.dte} ${data.dte === 1 ? "day" : "days"}`],
              ["ATM strike", num(data.atm_strike)],
              ["Lot size", num(firstLeg?.contract.lot_size)],
              ["Market data", providerLabel],
              [
                "Retrieved",
                `${retrievedLabel(data.provenance.received_at)} IST`,
              ],
            ].map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          <div className="chain-provenance">
            <span>
              On-demand snapshot · Retrieved{" "}
              {retrievedLabel(data.provenance.received_at)} IST
            </span>
            <span>
              {data.provenance.source_time
                ? `Source ${retrievedLabel(data.provenance.source_time)} IST · ${data.provenance.freshness.toLowerCase()}`
                : "Provider source time unavailable"}
              {data.provenance.cached ? " · Cached snapshot" : ""}
            </span>
            <span>
              Last retrieved data; continuous live updates and market session
              status are not implied.
            </span>
          </div>
          {(data.status === "PARTIAL" || data.warnings.length > 0) && (
            <div className="chain-notice" role="status">
              {[
                ...new Set([
                  ...(data.status === "PARTIAL"
                    ? [
                        "Partial chain. Available contracts and values are retained.",
                      ]
                    : []),
                  ...data.warnings.map(
                    (w) =>
                      chainMessages[w] || "Some chain evidence is unavailable.",
                  ),
                ]),
              ].map((m) => (
                <p key={m}>{m}</p>
              ))}
            </div>
          )}
          <div className="chain-layout">
            <div className="chain-card">
              <div className="chain-table-title">
                <h2>{data.underlying} option chain</h2>
                <span>{data.rows.length} strikes · Prices in INR</span>
              </div>
              <div
                className="chain-desktop"
                role="region"
                aria-label="Option chain table, scroll horizontally if needed"
                tabIndex={0}
              >
                <table aria-label="Calls and puts option chain">
                  <thead>
                    <tr>
                      <th
                        className="chain-call-head"
                        colSpan={7}
                        scope="colgroup"
                      >
                        CALLS · CE
                      </th>
                      <th className="chain-strike-head" scope="col">
                        STRIKE
                      </th>
                      <th
                        className="chain-put-head"
                        colSpan={7}
                        scope="colgroup"
                      >
                        PUTS · PE
                      </th>
                    </tr>
                    <tr>
                      {columns.map((c) => (
                        <th key={c} scope="col">
                          {c}
                        </th>
                      ))}
                      <th scope="col">INR</th>
                      {[...columns].reverse().map((c) => (
                        <th key={c} scope="col">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r) => (
                      <tr
                        key={r.strike}
                        className={r.is_atm ? "chain-atm" : undefined}
                      >
                        {cells(r.ce, "ce")}
                        <th scope="row" className="chain-strike">
                          {num(r.strike)}
                          {r.is_atm && <small>ATM</small>}
                        </th>
                        {cells(r.pe, "pe")}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="chain-mobile">
                <div className="chain-side-toggle" aria-label="Option side">
                  {(["ce", "pe"] as const).map((s) => (
                    <button
                      key={s}
                      aria-pressed={mobileSide === s}
                      onClick={() => setMobileSide(s)}
                    >
                      {s === "ce" ? "Calls" : "Puts"}
                    </button>
                  ))}
                </div>
                <table aria-label="Compact option chain">
                  <thead>
                    <tr>
                      {["Strike", "LTP", "OI", "Volume", "IV %"].map((c) => (
                        <th key={c} scope="col">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((r) => (
                      <tr
                        key={r.strike}
                        className={[
                          r.is_atm ? "chain-atm" : "",
                          r[mobileSide]?.moneyness
                            ? "chain-money-" +
                              r[mobileSide].moneyness.toLowerCase()
                            : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        <th scope="row">
                          {num(r.strike)}
                          {r.is_atm && <small>ATM</small>}
                        </th>
                        <td>
                          {r[mobileSide] ? legButton(r[mobileSide]) : "—"}
                        </td>
                        <td title={num(r[mobileSide]?.market.open_interest)}>
                          {compact(r[mobileSide]?.market.open_interest)}
                        </td>
                        <td title={num(r[mobileSide]?.market.volume)}>
                          {compact(r[mobileSide]?.market.volume)}
                        </td>
                        <td>{num(r[mobileSide]?.market.implied_volatility)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!data.rows.length && (
                <p className="chain-empty">
                  No listed contracts in this window.
                </p>
              )}
              <div className="chain-table-footer">
                <div className="chain-legend" aria-label="Moneyness legend">
                  <span>
                    <i className="chain-swatch chain-swatch-itm" />
                    ITM · In the money
                  </span>
                  <span>
                    <i className="chain-swatch chain-swatch-atm" />
                    ATM · Nearest strike
                  </span>
                  <span>
                    <i className="chain-swatch chain-swatch-otm" />
                    OTM · Out of the money
                  </span>
                </div>
                <span className="chain-window-info">
                  Showing {data.rows.length} strikes (±{windowSize}) · —
                  unavailable
                </span>
              </div>
            </div>
            <aside className="chain-detail" aria-label="Selected contract">
              {selected ? (
                <>
                  <div className="chain-detail-bar">
                    <span>Selected Contract</span>
                    <button type="button" onClick={() => setSelection("")}>
                      Clear
                    </button>
                  </div>
                  <div className="chain-detail-body">
                    <h2>
                      {selected.contract.underlying_symbol}{" "}
                      {expiryLabel(selected.contract.expiry)}{" "}
                      {num(selected.contract.strike)}{" "}
                      {selected.contract.option_type}
                    </h2>
                    <div className="chain-detail-badges">
                      <span
                        className={
                          "chain-badge chain-badge-" +
                          selected.contract.option_type.toLowerCase()
                        }
                      >
                        {selected.contract.option_type}
                      </span>
                      {selected.moneyness && (
                        <span
                          className={
                            "chain-badge chain-badge-" +
                            selected.moneyness.toLowerCase()
                          }
                        >
                          {selected.moneyness}
                        </span>
                      )}
                      <span className="chain-badge chain-badge-provider">
                        {selected.contract.exchange} · {providerLabel}
                      </span>
                    </div>
                    <p className="chain-detail-price">
                      {selected.market.ltp == null ? (
                        "—"
                      ) : (
                        <>₹{num(selected.market.ltp)}</>
                      )}
                    </p>
                    <span className="chain-detail-price-caption">
                      Last traded price · Provider snapshot
                    </span>
                    <dl className="chain-detail-metrics">
                      {[
                        ["Bid ₹", selected.market.bid],
                        ["Ask ₹", selected.market.ask],
                        ["Spread ₹", selected.market.spread],
                        ["Spread %", selected.market.spread_percent],
                        ["Volume", selected.market.volume],
                        ["Open interest", selected.market.open_interest],
                        ["ΔOI", selected.market.change_in_open_interest],
                        ["IV %", selected.market.implied_volatility],
                        ["Delta", selected.market.delta],
                        ["Gamma", selected.market.gamma],
                        ["Vega", selected.market.vega],
                        ["Theta", selected.market.theta],
                      ].map(([label, value]) => (
                        <div key={String(label)}>
                          <dt>{label}</dt>
                          <dd
                            className={
                              label === "ΔOI" ? signedClass(value) : undefined
                            }
                          >
                            {label === "ΔOI"
                              ? compact(value, true)
                              : label === "Volume" || label === "Open interest"
                                ? compact(value)
                                : num(value, label === "Gamma" ? 6 : 2)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                    <div className="chain-detail-characteristics">
                      <h3>Contract characteristics</h3>
                      <dl>
                        <div>
                          <dt>Expiry</dt>
                          <dd>{expiryLabel(selected.contract.expiry)}</dd>
                        </div>
                        <div>
                          <dt>Lot size</dt>
                          <dd>{num(selected.contract.lot_size)}</dd>
                        </div>
                        <div>
                          <dt>Strike</dt>
                          <dd>₹{num(selected.contract.strike)}</dd>
                        </div>
                        <div>
                          <dt>DTE</dt>
                          <dd>{data.dte} days</dd>
                        </div>
                      </dl>
                    </div>
                    <p className="chain-detail-source">
                      <strong>{providerLabel} market data</strong> · Retrieved{" "}
                      {retrievedLabel(data.provenance.received_at)} IST
                      <br />
                      {selected.market.source_time
                        ? "Source " +
                          retrievedLabel(selected.market.source_time) +
                          " IST"
                        : "Provider source time unavailable"}
                    </p>
                  </div>
                  {selected.availability !== "AVAILABLE" && (
                    <p role="note">
                      {selected.availability === "UNAVAILABLE"
                        ? "Quote unavailable"
                        : "Partial quote"}
                      . Broker preview checks the execution contract again.
                    </p>
                  )}
                  <details>
                    <summary>Greeks & contract details</summary>
                    <dl>
                      {[
                        ["Delta", selected.market.delta],
                        ["Gamma", selected.market.gamma],
                        ["Theta", selected.market.theta],
                        ["Vega", selected.market.vega],
                      ].map(([k, v]) => (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{num(v, 6)}</dd>
                        </div>
                      ))}
                    </dl>
                    <p>
                      Provider values only. Unavailable calculations remain
                      blank.
                    </p>
                  </details>
                  <div className="chain-trade">
                    <label>
                      Execution broker
                      <select
                        aria-label="Execution broker"
                        value={brokerId}
                        onChange={(e) => setBrokerId(e.target.value)}
                      >
                        <option value="">Select capable broker</option>
                        {brokers.map((b) => (
                          <option key={b.account.id} value={b.account.id}>
                            {b.account.name} · {b.account.provider}
                          </option>
                        ))}
                      </select>
                    </label>
                    {brokersLoaded && !brokers.length && (
                      <p>
                        Connect an options-capable broker in{" "}
                        <Link href="/brokers">Brokers</Link> to preview a trade.
                      </p>
                    )}
                    <div>
                      <button
                        className="chain-buy"
                        disabled={
                          !broker?.capability.broker.option_buy_supported ||
                          busy ||
                          !!error
                        }
                        onClick={() => open("BUY")}
                      >
                        Buy {selected.contract.option_type}
                      </button>
                      <button
                        className="chain-sell"
                        disabled={
                          !broker?.capability.broker.option_sell_supported ||
                          busy ||
                          !!error
                        }
                        onClick={() => open("SELL")}
                      >
                        Sell {selected.contract.option_type}
                      </button>
                    </div>
                    <small>
                      Opens the Broker V2 order ticket. Preview and explicit
                      confirmation are required.
                    </small>
                  </div>
                </>
              ) : (
                <div className="chain-empty chain-detail-empty">
                  <span className="chain-empty-icon" aria-hidden="true">
                    ◎
                  </span>
                  <h2>Select a contract</h2>
                  <p>
                    Choose a Call or Put price to inspect its quote, liquidity,
                    and exact contract before opening Broker V2 preview.
                  </p>
                </div>
              )}
            </aside>
          </div>
        </>
      ) : (
        !busy &&
        !error &&
        !expiryError && (
          <div className="chain-empty chain-card chain-landing">
            <span className="chain-empty-icon" aria-hidden="true">
              ▥
            </span>
            <h2>Explore an option chain</h2>
            <p>
              Search an underlying to inspect listed expiries, liquidity, open
              interest, and exact contracts.
            </p>
            <div className="chain-landing-capabilities">
              <span>Market data · Dhan</span>
              <span>Trading preview · Broker V2</span>
            </div>
          </div>
        )
      )}
      {ticket && (
        <OrderTicket
          account={ticket.account}
          canonical={ticket.canonical}
          close={() => setTicket(null)}
        />
      )}
    </section>
  );
}
