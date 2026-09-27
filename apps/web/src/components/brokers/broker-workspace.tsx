"use client";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Account,
  Provider,
  Snapshot,
  Row,
  Instrument,
  BrokerFunction,
  brokerApi,
  functions,
  title,
  newer,
  operational,
  stateLabel,
  readLabel,
} from "../../lib/brokers";

const link = (id: string, view = "overview") =>
  `/brokers/accounts/${id}/${view}`;
function Logo({ name }: { name: string }) {
  return (
    <span className="broker-logo" aria-hidden="true">
      {name.slice(0, 1)}
    </span>
  );
}
export function BrokerWorkspace({ path }: { path: string[] }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const sync = useCallback(async () => {
    try {
      const next = await brokerApi<Account[]>("accounts");
      setAccounts((old) =>
        next.map((a) =>
          newer(
            a,
            old.find((b) => b.id === a.id),
          ),
        ),
      );
      setError("");
      setLoaded(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    const initial = setTimeout(() => void sync(), 0);
    void brokerApi<Provider[]>("providers")
      .then(setProviders)
      .catch((e: Error) => setError(e.message));
    const timer = setInterval(() => void sync(), 15000);
    const onFocus = () => void sync();
    window.addEventListener("focus", onFocus);
    window.addEventListener("storage", onFocus);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("storage", onFocus);
    };
  }, [sync]);
  const merge = useCallback(
    (a: Account) =>
      setAccounts((old) => old.map((b) => (b.id === a.id ? newer(a, b) : b))),
    [],
  );
  async function action(account: Account, kind: "connect" | "disconnect") {
    setBusy(true);
    setError("");
    try {
      if (kind === "connect") {
        const result = await brokerApi<{ login_url: string }>(
          `accounts/${account.id}/connect`,
          {},
        );
        window.location.assign(result.login_url);
      } else {
        const disconnected = await brokerApi<Account>(
          `accounts/${account.id}/disconnect`,
          {},
        );
        merge(disconnected);
        try {
          localStorage.setItem(
            "twf-broker-change",
            account.updated_at + "-disconnected",
          );
        } catch {
          /* optional cross-tab notification */
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      void sync();
    }
  }
  const account =
    path[0] === "accounts" ? accounts.find((x) => x.id === path[1]) : undefined;
  const view = path[2] as BrokerFunction;
  const setup = path[0] === "setup" && path[1] === "zerodha";
  const manage = path[0] === "manage";
  const my = manage && path[1] === "my";
  const rooms = accounts.filter(operational);
  return (
    <section className="broker-workspace">
      <h1>{setup ? "Setup Zerodha" : manage ? "Manage Brokers" : "Brokers"}</h1>
      <nav
        className="broker-tabs broker-account-tabs"
        aria-label="Broker accounts"
      >
        <Link href="/brokers" aria-current={!path.length ? "page" : undefined}>
          Overview
        </Link>
        {rooms.map((a) => (
          <Link
            key={a.id}
            href={link(a.id)}
            aria-current={account?.id === a.id ? "page" : undefined}
          >
            {a.name}
          </Link>
        ))}
        <Link
          href="/brokers/manage"
          aria-current={manage || setup ? "page" : undefined}
        >
          Manage Brokers
        </Link>
      </nav>
      {error && (
        <div className="broker-notice" role="alert">
          {error} <button onClick={() => void sync()}>Retry</button>
        </div>
      )}
      {!loaded && !error && <p role="status">Loading broker connections…</p>}
      {setup ? (
        path[2] && !loaded ? (
          <p role="status">Loading connection…</p>
        ) : path[2] && !accounts.some((a) => a.id === path[2]) ? (
          <p>Broker account not found.</p>
        ) : (
          <Setup
            key={accounts.find((a) => a.id === path[2])?.id || "new"}
            account={accounts.find((a) => a.id === path[2])}
          />
        )
      ) : manage ? (
        <>
          <nav className="broker-tabs" aria-label="Manage brokers">
            <Link
              href="/brokers/manage"
              aria-current={!my ? "page" : undefined}
            >
              All Brokers
            </Link>
            <Link
              href="/brokers/manage/my"
              aria-current={my ? "page" : undefined}
            >
              My Brokers ({accounts.length})
            </Link>
          </nav>
          <div className="broker-toolbar">
            <label className="broker-search">
              <span className="sr-only">Search brokers</span>
              <input
                placeholder="Search brokers…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <label>
              <span className="sr-only">Broker availability</span>
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="all">All</option>
                <option value="supported">Supported</option>
              </select>
            </label>
          </div>
          <div className="broker-cards">
            {my
              ? accounts
                  .filter((a) =>
                    a.name.toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((a) => (
                    <article className="broker-card" key={a.id}>
                      <Logo name="Zerodha" />
                      <h2>{a.name}</h2>
                      <p
                        className={
                          a.state === "connected" ? "broker-positive" : "muted"
                        }
                      >
                        ● {stateLabel(a)}
                      </p>
                      <p className="muted">
                        {a.identity
                          ? `Account ${a.identity}`
                          : "Authentication required"}
                      </p>
                      <div className="broker-actions">
                        {operational(a) && (
                          <Link className="broker-button" href={link(a.id)}>
                            Open
                          </Link>
                        )}
                        {a.state !== "connected" && (
                          <button
                            disabled={busy}
                            onClick={() => void action(a, "connect")}
                          >
                            {a.identity ? "Reconnect" : "Connect"}
                          </button>
                        )}
                        <Link
                          className="broker-button"
                          href={`/brokers/setup/zerodha/${a.id}`}
                        >
                          Manage
                        </Link>
                        {a.state === "connected" && (
                          <button
                            disabled={busy}
                            onClick={() => void action(a, "disconnect")}
                          >
                            Disconnect
                          </button>
                        )}
                      </div>
                    </article>
                  ))
              : providers
                  .filter(
                    (p) =>
                      p.name.toLowerCase().includes(search.toLowerCase()) &&
                      (filter === "all" || p.supported),
                  )
                  .map((p) => {
                    const count = accounts.filter(
                      (a) => a.provider === p.id,
                    ).length;
                    return (
                      <article className="broker-card" key={p.id}>
                        <div className="broker-card-name">
                          <Logo name={p.name} />
                          <h2>{p.name}</h2>
                        </div>
                        <p className="muted">
                          {p.supported
                            ? "NSE · BSE · NFO · MCX"
                            : "Indian broker"}
                        </p>
                        <p>
                          {count
                            ? `${count} connection${count === 1 ? "" : "s"}`
                            : p.supported
                              ? "Supported · Read only"
                              : "Coming later"}
                        </p>
                        {p.supported ? (
                          <div className="broker-actions">
                            <Link
                              className="broker-button"
                              href={
                                count
                                  ? "/brokers/manage/my"
                                  : "/brokers/setup/zerodha"
                              }
                            >
                              {count ? "Manage" : "Setup"}
                            </Link>
                            {count > 0 && (
                              <Link
                                className="broker-button"
                                href="/brokers/setup/zerodha"
                              >
                                Add connection
                              </Link>
                            )}
                          </div>
                        ) : (
                          <button disabled>Coming later</button>
                        )}
                      </article>
                    );
                  })}
          </div>
          {my && loaded && !accounts.length && (
            <div className="broker-empty">
              <h2>No saved connections</h2>
              <p>Choose Zerodha in All Brokers to get started.</p>
              <Link className="broker-button primary" href="/brokers/manage">
                All Brokers
              </Link>
            </div>
          )}
        </>
      ) : path[0] === "accounts" ? (
        account && functions.includes(view) ? (
          <Room
            key={account.id}
            account={account}
            view={view}
            merge={merge}
            statusFailed={!!error}
            refreshAccounts={sync}
            disconnect={() => void action(account, "disconnect")}
            busy={busy}
          />
        ) : (
          loaded && (
            <div className="broker-empty">
              <h2>Broker account not found</h2>
              <Link href="/brokers/manage">Manage Brokers</Link>
            </div>
          )
        )
      ) : !path.length ? (
        <div className="broker-empty">
          <span className="broker-plug" aria-hidden="true">
            ⌁
          </span>
          <h2>
            {rooms.length ? "Your broker workspace" : "No broker connected yet"}
          </h2>
          <p>
            {rooms.length
              ? "Choose an account to view its read-only data."
              : "Connect a broker to start using TWF."}
          </p>
          {rooms.length ? (
            <div className="broker-actions">
              {rooms.map((a) => (
                <Link className="broker-button" key={a.id} href={link(a.id)}>
                  {a.name}
                </Link>
              ))}
            </div>
          ) : (
            <Link className="broker-button primary" href="/brokers/manage">
              Manage Brokers
            </Link>
          )}
          <div className="broker-helper">
            <h3>What you can do</h3>
            <ul>
              <li>Configure one or more broker connections</li>
              <li>Connect securely using the broker’s official login</li>
              <li>Connected accounts appear here automatically</li>
            </ul>
          </div>
        </div>
      ) : (
        <p>
          Page not found. <Link href="/brokers">Back to Brokers</Link>
        </p>
      )}
    </section>
  );
}

function Setup({ account }: { account?: Account }) {
  const [name, setName] = useState(account?.name || "Zerodha – Primary");
  const [key, setKey] = useState("");
  const [secret, setSecret] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState<{
    callback_url: string;
    storage_available: boolean;
    storage_message: string | null;
  } | null>(null);
  useEffect(() => {
    void brokerApi<typeof info>("setup")
      .then(setInfo)
      .catch((e: Error) => setError(e.message));
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const saved = await brokerApi<Account>("accounts", {
        provider: "zerodha",
        name,
        api_key: key,
        api_secret: secret,
        account_id: account?.id || null,
      });
      setKey("");
      setSecret("");
      const result = await brokerApi<{ login_url: string }>(
        `accounts/${saved.id}/connect`,
        {},
      );
      window.location.assign(result.login_url);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <div className="broker-setup">
      <div className="broker-toolbar">
        <Link href="/brokers/manage/my">← Back to brokers</Link>
        <a
          href="https://kite.trade/docs/connect/v3/user/"
          target="_blank"
          rel="noreferrer"
        >
          View help ↗
        </a>
      </div>
      <p className="broker-info">
        Enter your Kite Connect app details. You’ll complete login securely with
        Zerodha. Trading remains disabled.
      </p>
      {info && (
        <p className="broker-callback-url">
          Set this exact redirect URL in your Kite app:{" "}
          <code>{info.callback_url}</code>
        </p>
      )}
      {info && !info.storage_available && (
        <p role="alert" className="broker-notice">
          {info.storage_message ||
            "Credential encryption key is not configured. Set TWF_CREDENTIAL_MASTER_KEY and restart TWF."}{" "}
          See the local setup guide (docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md).
        </p>
      )}
      <form onSubmit={submit}>
        <label>
          Connection name
          <input
            required
            maxLength={80}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <div className="broker-form-grid">
          <label>
            API Key
            <input
              autoComplete="off"
              required
              minLength={8}
              maxLength={128}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="Enter API Key"
            />
          </label>
          <label>
            <span id="broker-secret-label">API Secret</span>
            <div className="broker-secret">
              <input
                aria-labelledby="broker-secret-label"
                autoComplete="new-password"
                required
                minLength={8}
                maxLength={128}
                type={visible ? "text" : "password"}
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="Enter API Secret"
              />
              <button
                type="button"
                aria-pressed={visible}
                aria-label={visible ? "Hide API secret" : "Show API secret"}
                onClick={() => setVisible(!visible)}
              >
                {visible ? "Hide" : "Show"}
              </button>
            </div>
          </label>
        </div>
        {account && (
          <p className="muted">
            Saved secrets are never shown. To update this connection, enter both
            app credentials again. The original broker account remains bound.
          </p>
        )}
        {error && (
          <p role="alert" className="broker-notice">
            {error}
          </p>
        )}
        <div className="broker-form-footer">
          <span className="muted">
            Your app secret stays on the TWF server.
          </span>
          <button
            className="primary"
            disabled={busy || !info?.storage_available}
          >
            {busy ? "Connecting…" : "Connect Broker"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Room({
  account,
  view,
  merge,
  statusFailed,
  refreshAccounts,
  disconnect,
  busy,
}: {
  account: Account;
  view: BrokerFunction;
  merge: (a: Account) => void;
  statusFailed: boolean;
  refreshAccounts: () => Promise<void>;
  disconnect: () => void;
  busy: boolean;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loadedKey, setLoadedKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [now, setNow] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [query, setQuery] = useState("");
  const [form, setForm] = useState({
    q: "",
    underlying: "",
    expiry: "",
    strike: "",
    kind: "",
  });
  const [page, setPage] = useState(1);
  const sequence = useRef(0);
  const key = `${view}?${query}&page=${page}`;
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const version = ++sequence.current;
    if (account.state !== "connected") return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setLoading(true);
        setError("");
      }
    });
    void brokerApi<Snapshot>(
      `accounts/${account.id}/${key}`,
      undefined,
      controller.signal,
    )
      .then((result) => {
        if (version !== sequence.current) return;
        setSnapshot(result);
        setLoadedKey(key);
        merge(result.account);
        setNow(Date.now());
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError" && version === sequence.current) {
          setError(e.message);
          void refreshAccounts();
        }
      })
      .finally(() => {
        if (version === sequence.current) setLoading(false);
      });
    return () => {
      controller.abort();
      sequence.current = version + 1;
    };
  }, [
    account.id,
    account.state,
    account.generation,
    key,
    refresh,
    merge,
    refreshAccounts,
  ]);
  const current = loadedKey === key ? snapshot : null;
  const freshness = readLabel(account, current, !!error || statusFailed, now);
  const label =
    view === "instruments" && freshness.startsWith("LIVE")
      ? "READ ONLY · DAILY INSTRUMENT LIST"
      : freshness;
  const data = current?.data;
  const catalog =
    data && !Array.isArray(data) && "items" in data && Array.isArray(data.items)
      ? (data as {
          items: Instrument[];
          total: number;
          limit: number;
          fetched_at: string;
        })
      : null;
  const values =
    data && !Array.isArray(data)
      ? (data as Record<string, number | string | null>)
      : null;
  return (
    <>
      <nav
        className="broker-tabs broker-function-tabs"
        aria-label="Broker functions"
      >
        {functions.map((v) => (
          <Link
            key={v}
            href={link(account.id, v)}
            aria-current={v === view ? "page" : undefined}
          >
            {title(v)}
          </Link>
        ))}
      </nav>
      <div className="broker-room-header">
        <div>
          <h2>
            {account.name}{" "}
            <span
              className={
                account.state === "connected"
                  ? "broker-positive broker-badge"
                  : "broker-badge"
              }
            >
              ● {stateLabel(account)}
            </span>
          </h2>
          <p role="status" className="broker-read-status">
            {label} · TRADING DISABLED
          </p>
        </div>
        <div className="broker-actions">
          <button
            onClick={() => setRefresh((x) => x + 1)}
            disabled={loading || account.state !== "connected"}
          >
            Refresh
          </button>
          <button
            onClick={disconnect}
            disabled={busy || account.state === "disconnected"}
          >
            Disconnect
          </button>
        </div>
      </div>
      {account.state !== "connected" && (
        <p className="broker-notice">
          This account needs a connection before data can be refreshed.{" "}
          <Link href="/brokers/manage/my">Manage connection</Link>
        </p>
      )}
      {error && (
        <p role="alert" className="broker-notice">
          {error} Retained data may be out of date.
        </p>
      )}
      {loading && <p role="status">Loading {view}…</p>}
      <h3 className="broker-view-title">{title(view)}</h3>
      {view === "instruments" && (
        <form
          className="broker-instrument-filters"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            setQuery(
              new URLSearchParams(
                Object.entries(form).filter(([, value]) => value),
              ).toString(),
            );
            setRefresh((x) => x + 1);
          }}
        >
          {(
            [
              ["q", "Search instruments", "Search HAL…"],
              ["underlying", "Underlying", "e.g. NIFTY"],
              ["expiry", "Expiry", "YYYY-MM-DD"],
              ["strike", "Strike", "Strike"],
            ] as const
          ).map(([field, text, placeholder]) => (
            <label key={field}>
              {text}
              <input
                type={
                  field === "expiry"
                    ? "date"
                    : field === "strike"
                      ? "number"
                      : "text"
                }
                min={field === "strike" ? 0 : undefined}
                step="any"
                maxLength={80}
                placeholder={placeholder}
                value={form[field]}
                onChange={(e) => setForm({ ...form, [field]: e.target.value })}
              />
            </label>
          ))}
          <label>
            Type
            <select
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              {["", "EQ", "CE", "PE", "FUT"].map((x) => (
                <option key={x} value={x}>
                  {x || "All"}
                </option>
              ))}
            </select>
          </label>
          <button disabled={loading || account.state !== "connected"}>
            Search
          </button>
        </form>
      )}
      {view === "overview" && values && (
        <>
          <div className="broker-summary">
            {[
              ["Available cash", values.cash],
              ["Holdings value", values.holdings_value],
              ["Positions", values.positions],
              ["Open orders", values.open_orders],
            ].map(([name, value]) => (
              <div key={String(name)}>
                <span>{name}</span>
                <strong>{display(value)}</strong>
              </div>
            ))}
          </div>
          <div className="broker-overview-bottom">
            <div className="broker-card">
              <h3>Recent activity</h3>
              <p>Account verified: {account.identity}</p>
              <p>
                Read completed{" "}
                {current
                  ? new Date(current.fetched_at).toLocaleTimeString()
                  : "—"}
              </p>
            </div>
            <div className="broker-card">
              <h3>Quick links</h3>
              {["holdings", "positions", "orders", "instruments"].map((v) => (
                <Link key={v} href={link(account.id, v)}>
                  {v === "instruments"
                    ? "Search Instruments"
                    : `View ${title(v)}`}{" "}
                  →
                </Link>
              ))}
            </div>
          </div>
        </>
      )}
      {view !== "overview" && current && (
        <ReadTable
          view={view}
          rows={
            catalog
              ? catalog.items.map((i) => ({ instrument: i }))
              : Array.isArray(data)
                ? data
                : []
          }
        />
      )}
      {catalog && (
        <div className="broker-pagination">
          <span>
            {catalog.total} instruments · Page {page} of{" "}
            {Math.max(1, Math.ceil(catalog.total / catalog.limit))}
          </span>
          <div className="broker-actions">
            <button
              disabled={page <= 1 || loading}
              onClick={() => setPage((x) => x - 1)}
            >
              Previous
            </button>
            <button
              disabled={page * catalog.limit >= catalog.total || loading}
              onClick={() => setPage((x) => x + 1)}
            >
              Next
            </button>
          </div>
          <span className="muted">
            Daily instrument list · Fetched{" "}
            {new Date(catalog.fetched_at).toLocaleString()}
          </span>
        </div>
      )}
      {current && (
        <p className="broker-asof muted">
          Read at {new Date(current.fetched_at).toLocaleString()} · On-demand
          snapshot
          {view === "instruments"
            ? " · Catalog prices are not live quotes"
            : " · INR"}
        </p>
      )}
    </>
  );
}
function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (
    (typeof value === "number" || typeof value === "string") &&
    Number.isFinite(Number(value))
  )
    return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
  return String(value);
}
const columns: Record<string, [string, string][]> = {
  holdings: [
    ["quantity", "Qty"],
    ["average", "Avg (₹)"],
    ["last_price", "LTP (₹)"],
    ["value", "Value (₹)"],
    ["pnl", "P&L (₹)"],
    ["pnl_percent", "P&L %"],
  ],
  positions: [
    ["product", "Product"],
    ["quantity", "Qty"],
    ["average", "Avg (₹)"],
    ["last_price", "LTP (₹)"],
    ["realized", "Realized"],
    ["unrealized", "Unrealized"],
    ["pnl", "Total P&L"],
  ],
  orders: [
    ["time", "Time (IST)"],
    ["side", "Side"],
    ["quantity", "Qty"],
    ["kind", "Type"],
    ["price", "Price (₹)"],
    ["status", "Status"],
  ],
  funds: [
    ["segment", "Segment"],
    ["enabled", "Enabled"],
    ["cash", "Available cash (₹)"],
    ["used_margin", "Used margin (₹)"],
    ["available_margin", "Available margin (₹)"],
    ["collateral", "Collateral (₹)"],
  ],
  instruments: [
    ["exchange", "Exchange"],
    ["segment", "Segment"],
    ["underlying", "Underlying"],
    ["expiry", "Expiry"],
    ["strike", "Strike"],
    ["kind", "Type"],
    ["native_token", "Native token"],
  ],
};
function ReadTable({ view, rows }: { view: string; rows: Row[] }) {
  if (!rows.length)
    return <p className="broker-empty-row">No {view} to show.</p>;
  return (
    <div
      className="broker-table-scroll"
      tabIndex={0}
      role="region"
      aria-label={`${title(view)} table`}
    >
      <table>
        <thead>
          <tr>
            {view !== "funds" && <th scope="col">Instrument</th>}
            {columns[view]?.map(([key, label]) => (
              <th scope="col" key={key}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const instrument = row.instrument as Instrument | undefined;
            const record =
              view === "instruments" ? (instrument as unknown as Row) : row;
            return (
              <tr key={String(row.id || i)}>
                {instrument && (
                  <th scope="row">
                    <strong>{instrument.symbol}</strong>
                    <small>{instrument.reference}</small>
                    {instrument.expiry && view !== "instruments" && (
                      <small>
                        {instrument.expiry} · {instrument.strike}{" "}
                        {instrument.kind}
                      </small>
                    )}
                  </th>
                )}
                {columns[view]?.map(([key]) => (
                  <td
                    key={key}
                    className={
                      ["pnl", "pnl_percent", "realized", "unrealized"].includes(
                        key,
                      ) && record[key] !== null
                        ? Number(record[key]) < 0
                          ? "broker-negative"
                          : "broker-positive"
                        : undefined
                    }
                  >
                    {key === "native_token"
                      ? String(record[key] || "—")
                      : display(record[key])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
