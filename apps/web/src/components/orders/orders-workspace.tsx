"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { QueueWorkspace } from "./queue-workspace";
import { QueueAdmissionDialog } from "./queue-admission-dialog";
import { TradePositions } from "./trade-positions";
import { twfQueueApi, type TWFQueueEntry } from "../../lib/twf-queue";
import { OrderTicket } from "../brokers/order-ticket";
import { brokerApi, type Account } from "../../lib/brokers";
import { money } from "../../lib/broker-orders";
import {
  twfOrdersApi,
  type TWFEvent,
  type TWFOrder,
} from "../../lib/twf-orders";

type DetailTab = "Overview" | "Instrument" | "Validation" | "History";

function displayDate(value: string) {
  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function StateBadge({ state }: { state: string }) {
  return (
    <span className={`twf-order-state twf-order-state-${state.toLowerCase()}`}>
      {state}
    </span>
  );
}

export function OrdersWorkspace() {
  const pathname = usePathname();
  const router = useRouter();
  const workspaceTab =
    pathname === "/trade/queue"
      ? "Queue"
      : pathname === "/trade/positions"
        ? "Positions"
        : "Orders";
  const [orders, setOrders] = useState<TWFOrder[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TWFOrder | null>(null);
  const [history, setHistory] = useState<TWFEvent[]>([]);
  const [tab, setTab] = useState<DetailTab>("Overview");
  const [ticket, setTicket] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [queueSelection, setQueueSelection] = useState<string | null>(null);
  const [queueRefreshKey, setQueueRefreshKey] = useState(0);
  const [confirmOrder, setConfirmOrder] = useState<TWFOrder | null>(null);
  const [queueBusy, setQueueBusy] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const rows = await twfOrdersApi<TWFOrder[]>("");
      setOrders(rows);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void Promise.resolve().then(refresh);
    void brokerApi<Account[]>("accounts")
      .then((rows) => {
        const connected = rows.filter(
          (account) => account.state === "connected",
        );
        setAccounts(connected);
        const stored = window.sessionStorage.getItem(
          "twf.trade.instrumentAccount",
        );
        setAccountId((current) =>
          connected.some((item) => item.id === current)
            ? current
            : connected.find((item) => item.id === stored)?.id ||
              connected[0]?.id ||
              "",
        );
      })
      .catch((e: Error) => setError(e.message));
    const requested = new URLSearchParams(window.location.search).get(
      "selected",
    );
    if (requested && /^[0-9a-f-]{36}$/i.test(requested)) {
      if (window.location.pathname === "/trade/queue")
        queueMicrotask(() => setQueueSelection(requested));
      else queueMicrotask(() => setSelectedId(requested));
    }
  }, [refresh]);
  useEffect(() => {
    if (accountId)
      window.sessionStorage.setItem("twf.trade.instrumentAccount", accountId);
  }, [accountId]);
  useEffect(() => {
    if (!selectedId) return;
    let cancelled = false;
    void Promise.all([
      twfOrdersApi<TWFOrder>(selectedId),
      twfOrdersApi<TWFEvent[]>(`${selectedId}/history`),
    ])
      .then(([order, events]) => {
        if (cancelled) return;
        setDetail(order);
        setHistory(events);
        setError("");
      })
      .catch((e: Error) => {
        if (!cancelled) setError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);
  async function viewInQueue(orderId: string) {
    try {
      const entry = await twfQueueApi<TWFQueueEntry>(`by-order/${orderId}`);
      setQueueSelection(entry.queue_entry_id);
      router.push(`/trade/queue?selected=${entry.queue_entry_id}`);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function admitConfirmed() {
    if (!confirmOrder || queueBusy) return;
    setQueueBusy(true);
    try {
      const entry = await twfQueueApi<TWFQueueEntry>("admit", {
        twf_order_id: confirmOrder.twf_order_id,
        expected_order_version: confirmOrder.version,
      });
      setDetail(entry.order);
      setConfirmOrder(null);
      setQueueSelection(entry.queue_entry_id);
      setQueueRefreshKey((value) => value + 1);
      router.push(`/trade/queue?selected=${entry.queue_entry_id}`);
      setError("");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      setConfirmOrder(null);
      await refresh();
    } finally {
      setQueueBusy(false);
    }
  }
  function viewOrder(orderId: string) {
    setSelectedId(orderId);
    setTab("Overview");
    router.push(`/trade/orders?selected=${orderId}`);
  }
  const account = accounts.find((item) => item.id === accountId);
  return (
    <section className="orders-workspace broker-workspace">
      <h1 className="sr-only">Trade</h1>
      <nav className="orders-workspace-tabs" aria-label="Trade sections">
        <div className="orders-tab-links">
          <Link
            href="/trade/orders"
            aria-current={workspaceTab === "Orders" ? "page" : undefined}
          >
            Orders
          </Link>
          <Link
            href="/trade/queue"
            aria-current={workspaceTab === "Queue" ? "page" : undefined}
          >
            Execution Queue
          </Link>
          <Link
            href="/trade/positions"
            aria-current={workspaceTab === "Positions" ? "page" : undefined}
          >
            Positions
          </Link>
        </div>
        <div className="orders-heading-actions">
          <label>
            Instrument account
            <select
              aria-label="Instrument account"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              {accounts.length === 0 && (
                <option value="">No connected account</option>
              )}
              {accounts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary"
            disabled={!account}
            onClick={() => setTicket(true)}
          >
            + New Order
          </button>
        </div>
      </nav>
      {workspaceTab === "Orders" && (
        <p className="orders-boundary" role="note">
          Creating a TWF Order records a validated intent. Queue admission
          requires a separate Add to Queue action. No broker submission occurs
          here.
        </p>
      )}
      {workspaceTab === "Orders" && !account && (
        <p className="broker-notice">
          Connect a Broker account to select a current instrument for a new TWF
          Order. Existing TWF Orders remain available below.
        </p>
      )}
      {error && (
        <p role="alert" className="broker-notice">
          {error} <button onClick={() => void refresh()}>Retry</button>
        </p>
      )}
      {workspaceTab === "Orders" ? (
        <div
          className={`orders-layout${selectedId ? " orders-layout-detail" : ""}`}
        >
          <section className="orders-list" aria-label="TWF Orders">
            <div className="orders-list-head">
              <h2>TWF Orders</h2>
              <span>{orders.length} recent</span>
            </div>
            {loading ? (
              <p role="status">Loading orders…</p>
            ) : orders.length === 0 ? (
              <div className="orders-empty">
                <strong>No TWF Orders yet</strong>
                <p>Use + New Order to prepare a manual order.</p>
              </div>
            ) : (
              <div className="orders-table-scroll">
                <table className="orders-table">
                  <thead>
                    <tr>
                      <th>Order ID</th>
                      <th>Created</th>
                      <th>Instrument</th>
                      <th>Side</th>
                      <th>Qty</th>
                      <th>Type</th>
                      <th>Price</th>
                      <th>Source</th>
                      <th>State</th>
                      <th>Queue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((order) => (
                      <tr
                        key={order.twf_order_id}
                        className={
                          selectedId === order.twf_order_id ? "selected" : ""
                        }
                      >
                        <td>
                          <button
                            className="orders-id"
                            onClick={() => {
                              setSelectedId(order.twf_order_id);
                              setTab("Overview");
                            }}
                            aria-label={`View order ${order.twf_order_id}`}
                          >
                            {order.twf_order_id.slice(0, 8)}…
                          </button>
                        </td>
                        <td>{displayDate(order.created_at)}</td>
                        <td>
                          <strong>{order.instrument.symbol}</strong>
                          <small>
                            {order.instrument.exchange} ·{" "}
                            {order.instrument.asset_class}
                          </small>
                        </td>
                        <td>{order.terms.side}</td>
                        <td>{order.terms.quantity}</td>
                        <td>{order.terms.order_type}</td>
                        <td>{money(order.terms.limit_price)}</td>
                        <td>{order.provenance.source}</td>
                        <td>
                          <StateBadge state={order.state} />
                        </td>
                        <td>
                          {order.state === "READY" && (
                            <button onClick={() => setConfirmOrder(order)}>
                              Add to Queue
                            </button>
                          )}
                          {order.state === "QUEUED" && (
                            <button
                              onClick={() =>
                                void viewInQueue(order.twf_order_id)
                              }
                            >
                              View in Queue
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="orders-list-note">
              Newest first · latest 50 · owner-scoped
            </p>
          </section>
          {selectedId && (
            <aside className="orders-detail" aria-label="Order details">
              <div className="orders-detail-head">
                <h2>Order Details</h2>
                <button
                  aria-label="Close order details"
                  onClick={() => setSelectedId(null)}
                >
                  ×
                </button>
              </div>
              {!detail || detail.twf_order_id !== selectedId ? (
                <p role="status">Loading order…</p>
              ) : (
                <>
                  <div className="orders-detail-summary">
                    <strong>{detail.instrument.symbol}</strong>
                    <StateBadge state={detail.state} />
                    <small>{detail.twf_order_id}</small>
                    {detail.state === "READY" && (
                      <button onClick={() => setConfirmOrder(detail)}>
                        Add to Queue
                      </button>
                    )}
                    {detail.state === "QUEUED" && (
                      <button
                        onClick={() => void viewInQueue(detail.twf_order_id)}
                      >
                        View in Queue
                      </button>
                    )}
                  </div>
                  <nav
                    className="orders-detail-tabs"
                    aria-label="Order detail sections"
                  >
                    {(
                      [
                        "Overview",
                        "Instrument",
                        "Validation",
                        "History",
                      ] as const
                    ).map((value) => (
                      <button
                        key={value}
                        aria-current={tab === value ? "page" : undefined}
                        onClick={() => setTab(value)}
                      >
                        {value}
                      </button>
                    ))}
                  </nav>
                  {tab === "Overview" && (
                    <dl className="orders-facts">
                      <div>
                        <dt>Order ID</dt>
                        <dd>{detail.twf_order_id}</dd>
                      </div>
                      <div>
                        <dt>State</dt>
                        <dd>{detail.state}</dd>
                      </div>
                      <div>
                        <dt>Source</dt>
                        <dd>{detail.provenance.source}</dd>
                      </div>
                      <div>
                        <dt>Source ref</dt>
                        <dd>{detail.provenance.source_ref || "—"}</dd>
                      </div>
                      <div>
                        <dt>Created</dt>
                        <dd>{displayDate(detail.created_at)}</dd>
                      </div>
                      <div>
                        <dt>Updated</dt>
                        <dd>{displayDate(detail.updated_at)}</dd>
                      </div>
                      <div>
                        <dt>Side</dt>
                        <dd>{detail.terms.side}</dd>
                      </div>
                      <div>
                        <dt>Quantity</dt>
                        <dd>{detail.terms.quantity}</dd>
                      </div>
                      <div>
                        <dt>Order type</dt>
                        <dd>{detail.terms.order_type}</dd>
                      </div>
                      <div>
                        <dt>Limit price</dt>
                        <dd>{money(detail.terms.limit_price)}</dd>
                      </div>
                      <div>
                        <dt>Product</dt>
                        <dd>{detail.terms.product}</dd>
                      </div>
                      <div>
                        <dt>Validity</dt>
                        <dd>{detail.terms.validity}</dd>
                      </div>
                    </dl>
                  )}
                  {tab === "Instrument" && (
                    <dl className="orders-facts">
                      <div>
                        <dt>Canonical ID</dt>
                        <dd>{detail.instrument.instrument_id}</dd>
                      </div>
                      <div>
                        <dt>Symbol</dt>
                        <dd>{detail.instrument.symbol}</dd>
                      </div>
                      <div>
                        <dt>Asset class</dt>
                        <dd>{detail.instrument.asset_class}</dd>
                      </div>
                      <div>
                        <dt>Exchange</dt>
                        <dd>{detail.instrument.exchange}</dd>
                      </div>
                      {detail.instrument.underlying_id && (
                        <div>
                          <dt>Underlying ID</dt>
                          <dd>{detail.instrument.underlying_id}</dd>
                        </div>
                      )}
                      {detail.instrument.expiry && (
                        <div>
                          <dt>Exchange expiry</dt>
                          <dd>{detail.instrument.expiry}</dd>
                        </div>
                      )}
                      {detail.instrument.strike && (
                        <div>
                          <dt>Strike</dt>
                          <dd>{detail.instrument.strike}</dd>
                        </div>
                      )}
                      {detail.instrument.option_type && (
                        <div>
                          <dt>Option type</dt>
                          <dd>{detail.instrument.option_type}</dd>
                        </div>
                      )}
                      {detail.instrument.lot_size && (
                        <div>
                          <dt>Lot size</dt>
                          <dd>{detail.instrument.lot_size}</dd>
                        </div>
                      )}
                      {detail.instrument.tick_size && (
                        <div>
                          <dt>Tick size</dt>
                          <dd>{detail.instrument.tick_size}</dd>
                        </div>
                      )}
                    </dl>
                  )}
                  {tab === "Validation" && (
                    <div className="orders-validation">
                      <StateBadge state={detail.state} />
                      <p>
                        {detail.state === "READY"
                          ? "Readiness validation passed. This order is ready for future Queue admission; no submission has occurred."
                          : "Review the recorded validation events below."}
                      </p>
                      {history
                        .filter(
                          (event) => event.event_type === "ORDER_VALIDATED",
                        )
                        .map((event) => (
                          <p key={event.event_id}>
                            Validation #{event.sequence}:{" "}
                            {event.details.ready === true
                              ? "Passed"
                              : Array.isArray(event.details.violations)
                                ? event.details.violations.join(", ")
                                : "Review required"}
                          </p>
                        ))}
                    </div>
                  )}
                  {tab === "History" && (
                    <ol className="orders-history">
                      {history.map((event) => (
                        <li key={event.event_id}>
                          <strong>
                            #{event.sequence} {event.event_type}
                          </strong>
                          <small>
                            {displayDate(event.occurred_at)} · {event.actor}
                          </small>
                          <span>
                            {event.from_state || "—"} → {event.to_state || "—"}
                            {event.reason ? ` · ${event.reason}` : ""}
                          </span>
                        </li>
                      ))}
                    </ol>
                  )}
                </>
              )}
            </aside>
          )}
        </div>
      ) : workspaceTab === "Queue" ? (
        <QueueWorkspace
          selectedId={queueSelection}
          onSelect={setQueueSelection}
          onViewOrder={viewOrder}
          refreshKey={queueRefreshKey}
        />
      ) : (
        <TradePositions account={account} />
      )}
      {confirmOrder && (
        <QueueAdmissionDialog
          order={confirmOrder}
          busy={queueBusy}
          onCancel={() => setConfirmOrder(null)}
          onConfirm={() => void admitConfirmed()}
        />
      )}
      {ticket && account && (
        <OrderTicket
          key={account.id}
          account={account}
          destination="TWF_ORDER"
          onCreated={(id) => {
            setSelectedId(id);
            setTab("Overview");
            void refresh();
          }}
          close={() => setTicket(false)}
        />
      )}
      <p className="orders-broker-link">
        Existing Broker New Order remains available in{" "}
        <Link href="/brokers">Brokers</Link> during the staged execution
        migration.
      </p>
    </section>
  );
}
