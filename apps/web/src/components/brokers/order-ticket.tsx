"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  freshQuote,
  quoteKey,
  quotePrice,
  useBrokerQuotes,
  type Quote,
} from "../../lib/broker-quotes";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { brokerApi, type Account, type Instrument } from "../../lib/brokers";
import {
  money,
  type Capability,
  type Choices,
  type Draft,
  type Intent,
  type Side,
} from "../../lib/broker-orders";

function instrumentLabel(instrument: Instrument): string {
  if (
    ["CE", "PE"].includes(instrument.kind || "") &&
    instrument.underlying &&
    instrument.expiry &&
    instrument.strike
  ) {
    const expiry = new Date(
      `${instrument.expiry}T00:00:00Z`,
    ).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    });
    return `${instrument.underlying} ${expiry} ${instrument.strike} ${instrument.kind}`;
  }
  return instrument.symbol;
}

export function OrderTicket({
  account,
  initial,
  recovery,
  close,
}: {
  account: Account;
  initial?: {
    instrument: Instrument;
    side: Side;
    quantity?: number;
    orderType?: string;
  };
  recovery?: Intent;
  close: () => void;
}) {
  const base = `accounts/${account.id}/order-entry/`;
  const pathname = usePathname();
  const [openedPath] = useState(pathname);
  const active = openedPath === pathname;
  useEffect(() => {
    if (!active) close();
  }, [active, close]);
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [stage, setStage] = useState<
    "select" | "ticket" | "preview" | "result"
  >(recovery ? "result" : initial ? "ticket" : "select");
  const [instrument, setInstrument] = useState<Instrument | null>(
    initial?.instrument || null,
  );
  const [side, setSide] = useState<Side>(initial?.side || "BUY");
  const [capability, setCapability] = useState<Capability | null>(null);
  const [intent, setIntent] = useState<Intent | null>(recovery || null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const priceInitialized = useRef(false);
  const priceUserModified = useRef(false);
  const launchQuote = useRef<Quote | undefined>(undefined);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    product: "",
    order_type: "",
    count: "1",
    price: "",
    trigger_price: "",
    validity: "",
  });
  useEffect(() => {
    const target = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => target?.focus();
  }, []);
  useEffect(() => {
    heading.current?.focus();
  }, [stage]);
  useEffect(() => {
    if (!instrument) return;
    const controller = new AbortController();
    const query = new URLSearchParams({
      reference: instrument.reference,
      native_token: instrument.native_token || "",
    });
    void brokerApi<Capability>(
      base + `capabilities?${query}`,
      undefined,
      controller.signal,
    )
      .then((c) => {
        if (!c.enabled || !c.instrument)
          throw new Error(
            "Manual trading is unavailable. Check your connection.",
          );
        if (controller.signal.aborted) return;
        setCapability(c);
        const selectedRule =
          c.order_types.find((r) => r.name === initial?.orderType) ||
          c.order_types.find((r) => r.name === "LIMIT") ||
          c.order_types[0];
        const launchPrice = selectedRule.price_required
          ? quotePrice(launchQuote.current, instrument.tick_size)
          : null;
        if (launchPrice !== null) priceInitialized.current = true;
        setForm({
          product: c.products[0],
          order_type: selectedRule.name,
          validity: selectedRule.validities[0],
          count: String(initial?.quantity || 1),
          price: launchPrice || "",
          trigger_price: "",
        });
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [base, instrument, initial?.orderType, initial?.quantity]);
  const rule = capability?.order_types.find((t) => t.name === form.order_type);
  const quotes = useBrokerQuotes(
    base,
    active && stage === "ticket" && instrument ? [instrument] : [],
  );
  const liveQuote = instrument ? quotes[quoteKey(instrument)] : undefined;
  const copyPrice = quotePrice(liveQuote, instrument?.tick_size);
  useEffect(() => {
    if (
      !active ||
      stage !== "ticket" ||
      !rule?.price_required ||
      copyPrice === null
    )
      return;
    // Cancel the pending initialization if the scope changes; manual input wins even
    // when it occurs between receipt and this first snapshot being applied.
    const timer = setTimeout(() => {
      if (priceInitialized.current || priceUserModified.current) return;
      priceInitialized.current = true;
      setForm((previous) => ({ ...previous, price: copyPrice }));
    }, 0);
    return () => clearTimeout(timer);
  }, [active, stage, rule?.price_required, copyPrice]);
  const lots = capability?.quantity_unit === "lots";
  const quantity =
    Number(form.count) * (lots ? Number(instrument?.lot_size) : 1);
  const indicativePrice = rule?.price_required
    ? Number(form.price)
    : freshQuote(liveQuote)
      ? Number(liveQuote?.price)
      : Number.NaN;
  async function preview() {
    if (!instrument?.native_token || !capability || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    const order: Draft = {
      reference: instrument.reference,
      native_token: instrument.native_token,
      side,
      product: form.product,
      order_type: form.order_type,
      quantity,
      lots: lots ? Number(form.count) : null,
      price: rule?.price_required ? form.price : undefined,
      trigger_price: rule?.trigger_required ? form.trigger_price : null,
      validity: form.validity,
    };
    try {
      setIntent(await brokerApi<Intent>(base + "preview", order));
      setStage("preview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function submit() {
    if (!intent || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      setIntent(
        await brokerApi<Intent>(base + `intents/${intent.id}/confirm`, {}),
      );
    } catch {
      setIntent({
        ...intent,
        status: "SUBMISSION_UNKNOWN",
        failure:
          "Submission status uncertain. Check Orders / Refresh before placing another order.",
      });
    } finally {
      setStage("result");
      lock.current = false;
      setBusy(false);
    }
  }
  async function reconcile() {
    if (!intent || lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      setIntent(
        await brokerApi<Intent>(base + `intents/${intent.id}/reconcile`, {}),
      );
    } catch {
      setError(
        "Unable to check broker orders. No order was resubmitted. Check Kite or refresh again.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  function select(item: Instrument, selectedSide: Side, quote?: Quote) {
    priceInitialized.current = false;
    priceUserModified.current = false;
    launchQuote.current = quote;
    setInstrument(item);
    setSide(selectedSide);
    setCapability(null);
    setError("");
    setStage("ticket");
  }
  const resultTitle =
    intent?.status === "SUBMITTED"
      ? "Order Submitted"
      : intent?.status === "BROKER_REJECTED"
        ? "Order Rejected"
        : intent?.status === "PREVIEWED"
          ? "Order not submitted"
          : "Submission status uncertain";
  if (!active) return null;
  return (
    <dialog
      ref={dialog}
      className="order-dialog"
      aria-labelledby="order-title"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else close();
      }}
    >
      <header className="order-titlebar">
        <h2 id="order-title" tabIndex={-1} ref={heading}>
          {stage === "select"
            ? "Select Instrument"
            : stage === "ticket"
              ? "Order Ticket"
              : stage === "preview"
                ? "Preview"
                : "Submission Result"}
        </h2>
        <button
          type="button"
          aria-label="Close order ticket"
          disabled={busy}
          onClick={close}
        >
          ×
        </button>
      </header>
      <ol className="order-steps" aria-label="Order progress">
        {["select", "ticket", "preview", "result"].map((s, i) => (
          <li key={s} aria-current={stage === s ? "step" : undefined}>
            {i + 1}.{" "}
            {s === "select"
              ? "Select"
              : s === "ticket"
                ? "Ticket"
                : s === "preview"
                  ? "Preview"
                  : "Result"}
          </li>
        ))}
      </ol>
      <div className="order-body">
        {error && (
          <p role="alert" id="order-error" className="broker-notice">
            {error}
          </p>
        )}
        {stage === "select" && <InstrumentPicker base={base} select={select} />}
        {stage === "ticket" && instrument && (
          <>
            <Contract
              instrument={instrument}
              quote={liveQuote}
              quoteAction={
                rule?.price_required && (
                  <button
                    type="button"
                    className="order-set-price"
                    disabled={copyPrice === null}
                    onClick={() => {
                      const price = quotePrice(liveQuote, instrument.tick_size);
                      if (price === null) return;
                      priceInitialized.current = true;
                      setForm((previous) => ({ ...previous, price }));
                    }}
                  >
                    Set Price
                  </button>
                )
              }
            />
            {freshQuote(liveQuote) &&
              copyPrice === null &&
              rule?.price_required && (
                <small className="muted">
                  Enter a price aligned to the contract tick size.
                </small>
              )}
            {!capability && !error && <p role="status">Checking contract…</p>}
            {capability && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void preview();
                }}
                aria-describedby={error ? "order-error" : undefined}
              >
                <div
                  className="order-side"
                  role="group"
                  aria-label="Order side"
                >
                  {(["BUY", "SELL"] as const).map((s) => (
                    <button
                      type="button"
                      key={s}
                      className={`order-${s.toLowerCase()}`}
                      aria-pressed={side === s}
                      onClick={() => setSide(s)}
                    >
                      {s === "BUY" ? "Buy" : "Sell"}
                    </button>
                  ))}
                </div>
                <div className="order-fields">
                  <label>
                    Product
                    <select
                      value={form.product}
                      onChange={(e) =>
                        setForm({ ...form, product: e.target.value })
                      }
                    >
                      {capability.products.map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Order type
                    <select
                      value={form.order_type}
                      onChange={(e) => {
                        const r = capability.order_types.find(
                          (t) => t.name === e.target.value,
                        )!;
                        setForm({
                          ...form,
                          order_type: r.name,
                          validity: r.validities[0],
                          trigger_price: "",
                        });
                      }}
                    >
                      {capability.order_types.map((t) => (
                        <option key={t.name}>{t.name}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {lots ? "Lots" : "Quantity"}
                    <input
                      required
                      type="number"
                      min="1"
                      step="1"
                      max={Math.floor(
                        capability.max_quantity /
                          (lots ? Number(instrument.lot_size) : 1),
                      )}
                      value={form.count}
                      onChange={(e) =>
                        setForm({ ...form, count: e.target.value })
                      }
                    />
                  </label>
                  {lots && (
                    <div className="order-lots">
                      <span>
                        Lot size <strong>{instrument.lot_size}</strong>
                      </span>
                      <span>
                        Quantity (auto){" "}
                        <output>
                          {Number.isFinite(quantity) ? quantity : "—"}
                        </output>
                      </span>
                    </div>
                  )}
                  {rule?.price_required && (
                    <label>
                      Price (₹)
                      <input
                        required
                        type="number"
                        min={instrument.tick_size || "0.01"}
                        step={instrument.tick_size || "any"}
                        value={form.price}
                        onChange={(e) => {
                          priceUserModified.current = true;
                          setForm({ ...form, price: e.target.value });
                        }}
                      />
                    </label>
                  )}
                  {rule?.trigger_required && (
                    <label>
                      Broker trigger price (₹)
                      <input
                        required
                        type="number"
                        min={instrument.tick_size || "0.01"}
                        step={instrument.tick_size || "any"}
                        value={form.trigger_price}
                        onChange={(e) =>
                          setForm({ ...form, trigger_price: e.target.value })
                        }
                      />
                      <small>Activates this broker stop-limit order.</small>
                    </label>
                  )}
                  <label>
                    Validity
                    <select
                      value={form.validity}
                      onChange={(e) =>
                        setForm({ ...form, validity: e.target.value })
                      }
                    >
                      {rule?.validities.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <dl className="order-totals">
                  <div>
                    <dt>Approx. order value</dt>
                    <dd>
                      {Number.isFinite(indicativePrice) && quantity > 0
                        ? money(indicativePrice * quantity)
                        : "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Estimated margin</dt>
                    <dd>—</dd>
                  </div>
                </dl>
                <fieldset disabled className="order-exits">
                  <legend>Exit Plan (optional)</legend>
                  {["Stop Loss", "Take Profit"].map((name) => (
                    <div key={name}>
                      <span>{name}</span>
                      <label>
                        Price
                        <input
                          aria-label={`${name} Price`}
                          placeholder="Price"
                        />
                      </label>
                      <label>
                        %
                        <input aria-label={`${name} Percent`} placeholder="%" />
                      </label>
                    </div>
                  ))}
                  <p>Managed exits will be enabled with TWF Alerts.</p>
                </fieldset>
                <div className="order-footer">
                  <button
                    type="button"
                    onClick={() => {
                      setStage("select");
                      setError("");
                    }}
                    disabled={busy}
                  >
                    Back
                  </button>
                  <button className="primary" disabled={busy || quantity <= 0}>
                    {busy
                      ? "Checking…"
                      : `Preview ${side === "BUY" ? "Buy" : "Sell"}`}
                  </button>
                </div>
              </form>
            )}
          </>
        )}
        {stage === "preview" && intent && (
          <>
            <div
              className={`order-preview order-${intent.order.side.toLowerCase()}`}
            >
              <strong>
                {intent.order.side} {instrumentLabel(intent.instrument)}
              </strong>
              <span>
                {intent.instrument.exchange} · {intent.instrument.segment}
              </span>
              <span>
                {intent.account_name} · {account.identity}
              </span>
            </div>
            <Contract instrument={intent.instrument} compact />
            <OrderSummary intent={intent} />
            {intent.warnings.map((warning) => (
              <p className="order-risk-warning" role="note" key={warning}>
                {warning}
              </p>
            ))}
            <p className="order-disclaimer">
              Broker acceptance depends on funds, RMS and exchange restrictions.
              This sends one live order. Preview expires in 5 minutes.
            </p>
            <div className="order-footer">
              <button disabled={busy} onClick={() => setStage("ticket")}>
                Back
              </button>
              <button
                className={`order-${intent.order.side.toLowerCase()} order-confirm`}
                disabled={busy}
                onClick={() => void submit()}
              >
                {busy
                  ? "Submitting…"
                  : `Confirm ${intent.order.side === "BUY" ? "Buy" : "Sell"}`}
              </button>
            </div>
          </>
        )}
        {stage === "result" && intent && (
          <div className="order-result">
            {intent.status === "SUBMITTED" && (
              <span className="order-success-mark" aria-hidden="true">
                ✓
              </span>
            )}
            <h3>{resultTitle}</h3>
            <p>
              {intent.order.side} {intent.order.quantity}{" "}
              {instrumentLabel(intent.instrument)}
              <br />
              {intent.order.order_type}
              {intent.order.price ? ` @ ${money(intent.order.price)}` : ""}
            </p>
            {intent.broker_order_id && (
              <p>
                Broker Order ID{" "}
                <strong className="order-id">{intent.broker_order_id}</strong>
              </p>
            )}
            {intent.provider_status && (
              <p>
                Broker status: <strong>{intent.provider_status}</strong>
              </p>
            )}
            {intent.status === "SUBMITTED" && (
              <p>Acknowledged by the broker. Execution is not guaranteed.</p>
            )}
            {intent.failure && <p role="status">{intent.failure}</p>}
            <Link
              className="broker-button"
              href={`/brokers/accounts/${account.id}/orders`}
              onClick={close}
            >
              View in Orders
            </Link>
            <button
              disabled={
                busy ||
                intent.status === "PREVIEWED" ||
                intent.status === "BROKER_REJECTED"
              }
              onClick={() => void reconcile()}
            >
              {busy ? "Checking…" : "Refresh broker status"}
            </button>
            {(intent.status === "SUBMITTED" ||
              intent.status === "BROKER_REJECTED" ||
              intent.status === "PREVIEWED") && (
              <button
                onClick={() => {
                  setIntent(null);
                  setInstrument(null);
                  setCapability(null);
                  setError("");
                  setStage("select");
                }}
              >
                Place Another Order
              </button>
            )}
            <small>Order intent {intent.id}</small>
          </div>
        )}
      </div>
    </dialog>
  );
}

function Contract({
  instrument: i,
  compact = false,
  quote,
  quoteAction,
}: {
  instrument: Instrument;
  compact?: boolean;
  quote?: Quote;
  quoteAction?: ReactNode;
}) {
  return (
    <div className="order-contract">
      {!compact && (
        <span className="order-initials" aria-hidden="true">
          {i.symbol.slice(0, 2)}
        </span>
      )}
      <div>
        <strong>{instrumentLabel(i)}</strong>
        {i.kind === "EQ" && i.name?.trim() && <small>{i.name}</small>}
        <small>
          {i.kind === "EQ"
            ? `${i.exchange} · Equity`
            : `${i.exchange} · ${i.kind} · Segment ${i.segment || "—"}`}
        </small>
        {i.expiry && (
          <small>
            Expiry {i.expiry} ·{" "}
            {i.kind !== "FUT" && `Strike ${i.strike} · ${i.kind} · `}Lot size{" "}
            {i.lot_size}
          </small>
        )}
        {!compact && (
          <div className="order-ltp">
            <small data-testid="reference-ltp">
              Reference / LTP: {freshQuote(quote) ? money(quote.price) : "—"}
            </small>
            {quoteAction}
          </div>
        )}
      </div>
    </div>
  );
}
function OrderSummary({ intent: i }: { intent: Intent }) {
  return (
    <dl className="order-summary">
      {[
        [
          "Instrument type",
          i.instrument_type === "OPTION"
            ? "Option"
            : i.instrument_type === "FUTURE"
              ? "Future"
              : "Equity",
        ],
        ...(i.option_contract
          ? [
              ["Underlying", i.option_contract.underlying_symbol],
              ["Expiry", i.option_contract.expiry],
              [
                "Strike / type",
                `${i.option_contract.strike} ${i.option_contract.option_type}`,
              ],
            ]
          : []),
        ["Product", i.order.product],
        ["Order type", i.order.order_type],
        ...(i.order.lots
          ? [["Lots", `${i.order.lots} (${i.instrument.lot_size} each)`]]
          : []),
        ["Quantity", i.order.quantity],
        ["Price", i.order.price ? money(i.order.price) : "Market"],
        ["Reference option LTP", money(i.reference_price)],
        ...(i.order.trigger_price
          ? [["Broker trigger", money(i.order.trigger_price)]]
          : []),
        ["Validity", i.order.validity],
        ["Estimated order value", money(i.estimated_value)],
        ...(i.premium_outlay
          ? [["Indicative premium outlay", money(i.premium_outlay)]]
          : []),
        ["Available cash", money(i.available_cash)],
        [
          "Estimated margin",
          i.margin_status === "AVAILABLE"
            ? money(i.estimated_margin)
            : "Margin estimate unavailable",
        ],
      ].map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
function InstrumentPicker({
  base,
  select,
}: {
  base: string;
  select: (i: Instrument, side: Side, quote?: Quote) => void;
}) {
  const [query, setQuery] = useState({
    asset: "equity",
    exchange: "NSE",
    q: "",
    underlying: "",
    expiry: "",
    option_type: "",
    strike: "",
    page: "1",
  });
  const [result, setResult] = useState<Choices | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState("");
  const search = new URLSearchParams(
    Object.entries(query).filter(
      ([key, value]) =>
        value && (key !== "exchange" || query.asset === "equity"),
    ),
  ).toString();
  const requestKey = base + search;
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void brokerApi<Choices>(
        base + `choices?${search}`,
        undefined,
        controller.signal,
      )
        .then((r) => {
          if (controller.signal.aborted) return;
          setResult(r);
          setLoaded(requestKey);
          setError("");
        })
        .catch((e: Error) => {
          if (!controller.signal.aborted) {
            setResult(null);
            setLoaded(requestKey);
            setError(e.message);
          }
        });
    }, 180);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [base, search, requestKey]);
  const current = loaded === requestKey ? result : null;
  const currentError = loaded === requestKey ? error : "";
  const results = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState<{ key: string; items: Instrument[] }>({
    key: "",
    items: [],
  });
  useEffect(() => {
    if (
      !current ||
      !results.current ||
      typeof IntersectionObserver === "undefined"
    )
      return;
    const indices = new Set<number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const index = Number(
            (entry.target as HTMLElement).dataset.quoteIndex,
          );
          if (entry.isIntersecting) indices.add(index);
          else indices.delete(index);
        }
        setVisible({
          key: requestKey,
          items: [...indices]
            .sort((a, b) => a - b)
            .map((i) => current.instruments[i]),
        });
      },
      { root: results.current.closest("dialog") },
    );
    results.current
      .querySelectorAll("[data-quote-index]")
      .forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [current, requestKey]);
  const quotes = useBrokerQuotes(
    base,
    current && visible.key === requestKey ? visible.items : [],
  );

  return (
    <div className="order-picker">
      <fieldset className="order-selection-group">
        <legend>Instrument Type</legend>
        <div>
          {(["equity", "futures", "options"] as const).map((asset) => (
            <label key={asset}>
              <input
                type="radio"
                name="instrument-type"
                value={asset}
                checked={query.asset === asset}
                onChange={() =>
                  setQuery({
                    asset,
                    exchange: "NSE",
                    q: "",
                    underlying: "",
                    expiry: "",
                    option_type: "",
                    strike: "",
                    page: "1",
                  })
                }
              />
              <span>
                {asset === "equity"
                  ? "Equity"
                  : asset === "futures"
                    ? "Futures"
                    : "Options"}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      {query.asset === "equity" && (
        <fieldset className="order-selection-group">
          <legend>Exchange</legend>
          <div>
            {["NSE", "BSE", "BOTH"].map((exchange) => (
              <label key={exchange}>
                <input
                  type="radio"
                  name="equity-exchange"
                  value={exchange}
                  checked={query.exchange === exchange}
                  onChange={() => setQuery({ ...query, exchange, page: "1" })}
                />
                <span>{exchange === "BOTH" ? "Both" : exchange}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <label>
        {query.asset === "equity" ? "Search stock" : "Search underlying"}
        <input
          type="search"
          maxLength={80}
          value={query.q}
          onChange={(e) =>
            setQuery({
              ...query,
              q: e.target.value,
              underlying: "",
              expiry: "",
              option_type: "",
              strike: "",
              page: "1",
            })
          }
          placeholder={
            query.asset === "equity" ? "Search RELIANCE…" : "Search NIFTY…"
          }
        />
      </label>
      {query.asset !== "equity" && (
        <>
          <label>
            Underlying
            <select
              value={query.underlying}
              onChange={(e) =>
                setQuery({
                  ...query,
                  underlying: e.target.value,
                  expiry: "",
                  option_type: "",
                  strike: "",
                  page: "1",
                })
              }
            >
              <option value="">Select underlying</option>
              {current?.underlyings.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Expiry
            <select
              value={query.expiry}
              disabled={!query.underlying}
              onChange={(e) =>
                setQuery({
                  ...query,
                  expiry: e.target.value,
                  option_type: "",
                  strike: "",
                  page: "1",
                })
              }
            >
              <option value="">Select expiry</option>
              {current?.expiries.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        </>
      )}
      {query.asset === "options" && (
        <>
          <label>
            Option type
            <select
              value={query.option_type}
              disabled={!query.expiry}
              onChange={(e) =>
                setQuery({
                  ...query,
                  option_type: e.target.value,
                  strike: "",
                  page: "1",
                })
              }
            >
              <option value="">Select type</option>
              {current?.option_types.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Strike
            <select
              value={query.strike}
              disabled={!query.option_type}
              onChange={(e) =>
                setQuery({ ...query, strike: e.target.value, page: "1" })
              }
            >
              <option value="">Select strike</option>
              {current?.strikes.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        </>
      )}
      {currentError && <p role="alert">{currentError}</p>}
      {!current && !currentError && (
        <p role="status">Loading valid contracts…</p>
      )}
      <div ref={results} className="order-choices">
        {current?.instruments.map((i, index) => (
          <div
            className="order-choice"
            data-quote-index={index}
            key={`${i.reference}:${i.native_token}`}
          >
            <Contract instrument={i} quote={quotes[quoteKey(i)]} />
            <div className="order-side">
              {(["BUY", "SELL"] as const).map((side) => (
                <button
                  key={side}
                  className={`order-${side.toLowerCase()} order-confirm`}
                  onClick={() => select(i, side, quotes[quoteKey(i)])}
                  aria-label={`${side === "BUY" ? "Buy" : "Sell"} ${i.symbol}`}
                >
                  {side === "BUY" ? "Buy" : "Sell"}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {current && !current.instruments.length && (
        <p className="muted">
          {query.asset === "equity"
            ? query.q.trim()
              ? "No matching executable instruments."
              : "Search for a stock to continue."
            : "Choose a listed contract to continue."}
        </p>
      )}
      {current && current.total > 30 && (
        <div className="order-footer">
          <button
            disabled={query.page === "1"}
            onClick={() =>
              setQuery({ ...query, page: String(Number(query.page) - 1) })
            }
          >
            Previous
          </button>
          <span>Page {query.page}</span>
          <button
            disabled={Number(query.page) * 30 >= current.total}
            onClick={() =>
              setQuery({ ...query, page: String(Number(query.page) + 1) })
            }
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
