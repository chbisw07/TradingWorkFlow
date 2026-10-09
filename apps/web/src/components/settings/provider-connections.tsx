"use client";
import Link from "next/link";
import { useSettingsSectionLink } from "./settings-section-link";

import { useCallback, useEffect, useState } from "react";
import { discoveryApi, type ProviderStatus } from "../../lib/discovery";

type ConnectionState =
  | "DISCONNECTED"
  | "DISCONNECTING"
  | "REAUTH_DRAINING"
  | "AUTH_REQUIRED"
  | "CONNECTING"
  | "CONNECTED"
  | "REAUTH_REQUIRED";

type Registration = {
  provider_id: string;
  display_name: string;
  auth_mode: "NONE" | "API_KEY" | "OAUTH_2_1";
  category: "MARKET_INTELLIGENCE" | "OTHER";
};

type Connection = {
  id: string;
  provider_id: string;
  display_name: string;
  enabled: boolean;
  generation: number;
  state: ConnectionState;
  health: "UNKNOWN" | "AVAILABLE" | "DEGRADED" | "UNAVAILABLE";
  error: string | null;
  cleanup_pending: boolean;
  operations_pending: number;
  unresolved_cleanup_count?: number;
  last_failure_at?: string | null;
  last_failure_kind?: string | null;
  recovery_required: boolean;
  tools: { name: string }[];
  last_success_at: string | null;
};

type Authorization = { authorization_url: string; generation: number };

type DhanState =
  | "NOT_CONFIGURED"
  | "CONFIGURED"
  | "READY"
  | "AUTH_FAILED"
  | "RATE_LIMITED"
  | "PROVIDER_ERROR"
  | "DISABLED";

type DhanStatus = {
  state: DhanState;
  configured: boolean;
  enabled: boolean;
  generation: number;
  source: "DATABASE" | "ENVIRONMENT" | "NONE";
  checked_at: string | null;
  last_error: string | null;
};

async function dhanApi<T>(path = "", method = "GET", body?: unknown) {
  const response = await fetch("/api/v1/settings/market-data/dhan" + path, {
    method,
    cache: "no-store",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: { code?: string };
    } | null;
    const code = payload?.error?.code || "";
    throw new Error(
      response.status === 401
        ? "Your session has expired. Sign in again."
        : response.status === 409 || code === "STALE_GENERATION"
          ? "The Dhan configuration changed elsewhere. Reload its current state."
          : response.status === 422
            ? "Enter a valid Dhan client ID and access token."
            : code === "SECRET_STORE_UNAVAILABLE"
              ? "Encrypted credential storage is unavailable. Configure the server credential master key."
              : "The Dhan configuration operation was not completed.",
    );
  }
  return response.json() as Promise<T>;
}

async function mcpApi<T>(path: string, method = "GET", body?: unknown) {
  const response = await fetch("/api/v1/settings/mcp/" + path, {
    method,
    cache: "no-store",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      error?: { code?: string };
    } | null;
    const code = payload?.error?.code || "";
    throw new Error(
      response.status === 404 || code === "NOT_CONFIGURED"
        ? "This provider is not registered in the API environment."
        : response.status === 401
          ? "Your session or provider authorization has expired."
          : response.status === 409
            ? "The connection changed elsewhere. Reload its current state."
            : response.status === 429
              ? "The provider is rate limited. Retry after its window resets."
              : "The provider connection operation was not completed.",
    );
  }
  return response.json() as Promise<T>;
}

function words(value: string) {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (c) => c.toUpperCase());
}

function connectionStatus(connection: Connection) {
  if (connection.error === "RATE_LIMITED") return "Rate limited";
  if (
    connection.state === "AUTH_REQUIRED" ||
    connection.state === "REAUTH_REQUIRED"
  )
    return "Authentication required";
  if (connection.state === "DISCONNECTED") return "Not connected";
  if (
    connection.state === "DISCONNECTING" ||
    connection.state === "REAUTH_DRAINING"
  )
    return "Disconnecting";
  if (connection.state === "CONNECTED" && connection.health === "AVAILABLE")
    return "Ready";
  if (connection.health === "DEGRADED") return "Degraded";
  if (connection.health === "UNAVAILABLE") return "Error";
  return "Connected";
}

export function ProviderConnectionsSection() {
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus[]>([]);
  const [dhanStatus, setDhanStatus] = useState<DhanStatus | null>(null);
  const [editDhan, setEditDhan] = useState(false);
  const [dhanClientId, setDhanClientId] = useState("");
  const [dhanAccessToken, setDhanAccessToken] = useState("");
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [configured, rows, statuses, dhanConfiguration] = await Promise.all(
        [
          mcpApi<Registration[]>("providers"),
          mcpApi<Connection[]>("connections"),
          discoveryApi<ProviderStatus[]>("status"),
          dhanApi<DhanStatus>(),
        ],
      );
      setRegistrations(
        configured.filter(
          (item) =>
            item.provider_id !== "tradingview" &&
            item.category === "MARKET_INTELLIGENCE",
        ),
      );
      setConnections(rows.filter((item) => item.provider_id !== "tradingview"));
      setProviderStatus(statuses);
      setDhanStatus(dhanConfiguration);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

  const hasActiveOperations = connections.some(
    (row) => row.operations_pending > 0,
  );
  useEffect(() => {
    if (!hasActiveOperations || pending) return;
    let cancelled = false;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout>;
    const refreshActive = async () => {
      try {
        const rows = await mcpApi<Connection[]>("connections");
        if (cancelled) return;
        setConnections((current) =>
          current.map(
            (old) =>
              rows.find(
                (row) => row.id === old.id && row.generation >= old.generation,
              ) || old,
          ),
        );
        attempts += 1;
        if (rows.some((row) => row.operations_pending > 0) && attempts < 20) {
          timer = setTimeout(() => void refreshActive(), 2000);
        }
      } catch {
        if (!cancelled)
          setError(
            "Provider status could not be refreshed. Reload status to check current operations.",
          );
      }
    };
    timer = setTimeout(() => void refreshActive(), 2000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [hasActiveOperations, pending]);

  async function run(action: () => Promise<void>) {
    setPending(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  }

  async function create(registration: Registration) {
    await run(async () => {
      const row = await mcpApi<Connection>("connections", "POST", {
        provider_id: registration.provider_id,
        display_name: registration.display_name,
      });
      setConnections((current) => [
        ...current.filter((item) => item.provider_id !== row.provider_id),
        row,
      ]);
      setNotice(`${registration.display_name} connection created.`);
    });
  }

  async function authorize(connection: Connection) {
    await run(async () => {
      const result = await mcpApi<Authorization>(
        `connections/${connection.id}/authorize`,
        "POST",
        { generation: connection.generation },
      );
      sessionStorage.setItem("twf.mcp.connection_id", connection.id);
      sessionStorage.setItem("twf.mcp.provider_name", connection.display_name);
      window.location.assign(result.authorization_url);
    });
  }

  async function connect(connection: Connection, registration: Registration) {
    await run(async () => {
      const apiKey = keys[connection.id]?.trim();
      const row = await mcpApi<Connection>(
        `connections/${connection.id}/connect`,
        "POST",
        {
          generation: connection.generation,
          api_key: registration.auth_mode === "API_KEY" ? apiKey : null,
        },
      );
      setKeys((current) => ({ ...current, [connection.id]: "" }));
      replaceConnection(row);
      setNotice(
        `${connection.display_name} connected. Test the connection to verify its required capabilities.`,
      );
    });
  }

  async function saveDhan() {
    if (!dhanStatus) return;
    await run(async () => {
      const row = await dhanApi<DhanStatus>("/credentials", "PUT", {
        generation: dhanStatus.generation,
        client_id: dhanClientId.trim(),
        access_token: dhanAccessToken,
      });
      setDhanStatus(row);
      setDhanClientId("");
      setDhanAccessToken("");
      setEditDhan(false);
      setNotice(
        "Dhan credentials saved. Test the connection before running a real scan.",
      );
    });
  }

  async function testDhan() {
    if (!dhanStatus) return;
    await run(async () => {
      const row = await dhanApi<DhanStatus>("/test", "POST", {
        generation: dhanStatus.generation,
      });
      setDhanStatus(row);
      setNotice(
        row.state === "READY"
          ? "Dhan connection verified and ready for real scans."
          : row.state === "AUTH_FAILED"
            ? "Dhan rejected the saved credentials. Update them and test again."
            : row.state === "RATE_LIMITED"
              ? "Dhan rate limited the connection test. Retry later."
              : "Dhan could not complete the connection test.",
      );
    });
  }

  async function disconnectDhan() {
    if (!dhanStatus) return;
    await run(async () => {
      const row = await dhanApi<DhanStatus>("/disconnect", "POST", {
        generation: dhanStatus.generation,
      });
      setDhanStatus(row);
      setDhanClientId("");
      setDhanAccessToken("");
      setEditDhan(false);
      setNotice(
        "Dhan market-data access disabled and saved credentials removed.",
      );
    });
  }

  function replaceConnection(row: Connection) {
    setConnections((current) =>
      current.map((item) => (item.id === row.id ? row : item)),
    );
  }

  async function operation(
    connection: Connection,
    action: "refresh" | "disconnect" | "test" | "cleanup" | "recover",
  ) {
    await run(async () => {
      const row = await mcpApi<Connection>(
        `connections/${connection.id}/${action}`,
        "POST",
        action === "cleanup" || action === "recover"
          ? undefined
          : { generation: connection.generation },
      );
      replaceConnection(row);
      setNotice(
        action === "test"
          ? `${connection.display_name}: ${connectionStatus(row)}.`
          : `${connection.display_name}: ${words(action)} completed.`,
      );
    });
  }

  const dhan = providerStatus.find((item) => item.id === "dhan");
  const dhanLabel: Record<DhanState, string> = {
    NOT_CONFIGURED: "Authentication required",
    CONFIGURED: "Configured",
    READY: "Ready",
    AUTH_FAILED: "Authentication failed",
    RATE_LIMITED: "Rate limited",
    PROVIDER_ERROR: "Provider error",
    DISABLED: "Disabled",
  };
  const dhanReady = dhanStatus?.state === "READY";
  useSettingsSectionLink("integrations", loaded);

  return (
    <section
      id="integrations"
      tabIndex={-1}
      aria-labelledby="provider-connections-heading"
    >
      <h2 id="provider-connections-heading">Data providers</h2>
      <p className="broker-settings-link">
        Trading accounts:{" "}
        <Link className="text-link" href="/brokers">
          Manage broker connections
        </Link>
      </p>
      <p>
        Market data and optional intelligence connections are managed
        separately.
      </p>

      {!loaded && <p role="status">Loading provider connections…</p>}
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button disabled={pending} onClick={() => void load()}>
            Reload providers
          </button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}

      <div className="settings-integration-card">
        <div className="settings-integration-heading">
          <div>
            <h3>Dhan market data</h3>
            <p>Authoritative instruments, quotes, and OHLCV for real scans.</p>
          </div>
          <span className={dhanReady ? "status-success" : "status-warning"}>
            {dhanStatus ? dhanLabel[dhanStatus.state] : "Loading"}
          </span>
        </div>
        {dhanStatus?.state === "CONFIGURED" && (
          <p>
            Credentials are saved. Test the connection to enable real scans.
          </p>
        )}
        {dhanStatus?.state === "AUTH_FAILED" && (
          <p>
            Dhan rejected the saved credentials. Replace them and test again.
          </p>
        )}
        {dhanStatus?.state === "RATE_LIMITED" && (
          <p>Dhan rate limited the last test. Retry after its window resets.</p>
        )}
        {dhanStatus?.state === "PROVIDER_ERROR" && (
          <p>Dhan could not complete the last connection test.</p>
        )}
        {dhanStatus?.source === "ENVIRONMENT" && (
          <p>
            Bootstrap credentials are supplied by the local API environment.
          </p>
        )}
        {!dhanStatus?.configured && dhan?.last_error && (
          <p>{dhan.last_error}</p>
        )}

        {editDhan && dhanStatus && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void saveDhan();
            }}
          >
            <label>
              <span>Dhan client ID</span>
              <input
                autoComplete="off"
                maxLength={128}
                required
                value={dhanClientId}
                onChange={(event) => setDhanClientId(event.target.value)}
              />
            </label>
            <p>The client ID assigned to your Dhan account.</p>
            <label>
              <span>Dhan access token</span>
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={4096}
                required
                value={dhanAccessToken}
                onChange={(event) => setDhanAccessToken(event.target.value)}
              />
            </label>
            <p>
              Access tokens are encrypted by the API and are never displayed
              again after saving.
            </p>
            <div className="settings-actions">
              <button
                type="submit"
                disabled={
                  pending || !dhanClientId.trim() || dhanAccessToken.length < 8
                }
              >
                Save Dhan credentials
              </button>
              <button
                type="button"
                disabled={pending}
                onClick={() => {
                  setEditDhan(false);
                  setDhanClientId("");
                  setDhanAccessToken("");
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {!editDhan && dhanStatus && (
          <div className="settings-actions">
            <button disabled={pending} onClick={() => setEditDhan(true)}>
              {dhanStatus.configured ? "Update credentials" : "Configure Dhan"}
            </button>
            {dhanStatus.configured && dhanStatus.enabled && (
              <>
                <button disabled={pending} onClick={() => void testDhan()}>
                  Test Dhan connection
                </button>
                <button
                  disabled={pending}
                  onClick={() => void disconnectDhan()}
                >
                  Disconnect Dhan
                </button>
              </>
            )}
            <button disabled={pending} onClick={() => void load()}>
              Reload Dhan status
            </button>
          </div>
        )}
        {dhanStatus?.checked_at && (
          <p>Last tested: {new Date(dhanStatus.checked_at).toLocaleString()}</p>
        )}
      </div>

      <h3>Market intelligence connections</h3>
      <p>
        Optional, owner-scoped MCP providers enrich context and never block
        technical scanning.
      </p>
      {loaded && registrations.length === 0 && (
        <p>No market-intelligence MCP providers are configured.</p>
      )}
      {registrations.map((registration) => {
        const connection = connections.find(
          (item) => item.provider_id === registration.provider_id,
        );
        if (!connection) {
          return (
            <div
              className="settings-integration-card"
              key={registration.provider_id}
            >
              <h3>{registration.display_name}</h3>
              <p>
                Market intelligence provider · {words(registration.auth_mode)}
              </p>
              <button
                disabled={pending}
                onClick={() => void create(registration)}
              >
                Add {registration.display_name} connection
              </button>
            </div>
          );
        }
        const authorized =
          connection.state === "CONNECTED" && connection.enabled;
        const ready = authorized && connection.health === "AVAILABLE";
        const registrationChanged = connection.error === "STALE_GENERATION";
        const status = connectionStatus(connection);
        return (
          <div className="settings-integration-card" key={connection.id}>
            <div className="settings-integration-heading">
              <div>
                <h3>{connection.display_name}</h3>
                <p>
                  State: <strong>{words(connection.state)}</strong> · Health:{" "}
                  <strong>{words(connection.health)}</strong>
                </p>
              </div>
              <span className={ready ? "status-success" : "status-warning"}>
                {status}
              </span>
            </div>
            <p>
              Generation {connection.generation} · {connection.tools.length}{" "}
              tools discovered · Active operations:{" "}
              {connection.operations_pending}
            </p>
            {!!connection.unresolved_cleanup_count && (
              <p>Unresolved cleanup: {connection.unresolved_cleanup_count}</p>
            )}
            {connection.last_failure_at && (
              <p>
                Last failure:{" "}
                {words(connection.last_failure_kind || "Unavailable")}
                {" · "}
                {new Date(connection.last_failure_at).toLocaleString()}
              </p>
            )}
            {connection.error === "TOOL_NOT_FOUND" && (
              <p>
                Required market-intelligence capabilities were not discovered.
                Reload or test again after the provider makes them available.
              </p>
            )}
            {connection.error === "RATE_LIMITED" && (
              <p>
                The provider is rate limited. Retry after its window resets.
              </p>
            )}
            {connection.last_success_at && (
              <p>
                Last provider success:{" "}
                {new Date(connection.last_success_at).toLocaleString()}
              </p>
            )}
            {registration.auth_mode === "API_KEY" && !authorized && (
              <label>
                <span>Personal access token</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={keys[connection.id] || ""}
                  onChange={(event) =>
                    setKeys((current) => ({
                      ...current,
                      [connection.id]: event.target.value,
                    }))
                  }
                />
              </label>
            )}
            <div className="settings-actions">
              {!authorized &&
                !registrationChanged &&
                connection.state !== "DISCONNECTING" &&
                (registration.auth_mode === "OAUTH_2_1" ? (
                  <button
                    disabled={pending}
                    onClick={() => void authorize(connection)}
                  >
                    {connection.state === "REAUTH_REQUIRED"
                      ? "Reauthorize"
                      : "Authorize"}{" "}
                    {connection.display_name}
                  </button>
                ) : (
                  <button
                    disabled={
                      pending ||
                      (registration.auth_mode === "API_KEY" &&
                        !(keys[connection.id] || "").trim())
                    }
                    onClick={() => void connect(connection, registration)}
                  >
                    Connect {connection.display_name}
                  </button>
                ))}
              {registrationChanged && (
                <button
                  disabled={pending}
                  onClick={() => void create(registration)}
                >
                  Create replacement connection
                </button>
              )}
              {authorized && (
                <>
                  <button
                    disabled={pending}
                    onClick={() => void operation(connection, "test")}
                  >
                    Test connection
                  </button>
                  {registration.auth_mode === "OAUTH_2_1" && (
                    <button
                      disabled={pending}
                      onClick={() => void operation(connection, "refresh")}
                    >
                      Refresh authorization
                    </button>
                  )}
                </>
              )}
              {connection.enabled && (
                <button
                  disabled={pending}
                  onClick={() => void operation(connection, "disconnect")}
                >
                  Disconnect
                </button>
              )}
              {connection.cleanup_pending && (
                <button
                  disabled={pending}
                  onClick={() => void operation(connection, "cleanup")}
                >
                  Retry cleanup
                </button>
              )}
              {connection.recovery_required && (
                <button
                  disabled={pending}
                  onClick={() => void operation(connection, "recover")}
                >
                  Recover connection
                </button>
              )}
              <button disabled={pending} onClick={() => void load()}>
                Reload status
              </button>
            </div>
          </div>
        );
      })}
    </section>
  );
}
