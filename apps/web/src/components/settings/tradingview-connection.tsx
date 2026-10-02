"use client";

import { useCallback, useEffect, useState } from "react";

type ConnectionState =
  | "DISCONNECTED"
  | "DISCONNECTING"
  | "REAUTH_DRAINING"
  | "AUTH_REQUIRED"
  | "CONNECTING"
  | "CONNECTED"
  | "REAUTH_REQUIRED";

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
  recovery_required: boolean;
  tools: { name: string }[];
  last_success_at: string | null;
};

type Authorization = {
  authorization_url: string;
  generation: number;
};

async function mcpApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/v1/settings/mcp/" + path, {
    method,
    cache: "no-store",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let code = "";
    try {
      const payload = (await response.json()) as {
        error?: { code?: string };
      };
      code = payload.error?.code || "";
    } catch {
      // The status still determines a safe user-facing message.
    }
    throw new Error(
      response.status === 404 || code === "NOT_CONFIGURED"
        ? "TradingView is not registered in the API environment. Configure TWF_MCP_PROVIDERS and restart the API."
        : response.status === 401
          ? "Your TWF session or TradingView authorization has expired."
          : response.status === 409
            ? "The connection changed elsewhere. Reload its current state."
            : response.status === 429
              ? "TradingView is rate limited. Retry after the provider window resets."
              : "The TradingView connection operation was not completed.",
    );
  }
  return response.json() as Promise<T>;
}

export function TradingViewConnectionSection() {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const rows = await mcpApi<Connection[]>("connections");
      setConnection(
        rows.find((item) => item.provider_id === "tradingview") || null,
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load]);

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

  async function createConnection() {
    await run(async () => {
      const row = await mcpApi<Connection>("connections", "POST", {
        provider_id: "tradingview",
        display_name: "TradingView",
      });
      setConnection(row);
      setNotice(
        "TradingView connection created. Authorize it to enable real evidence.",
      );
    });
  }

  async function authorize() {
    if (!connection) return;
    await run(async () => {
      const result = await mcpApi<Authorization>(
        "connections/" + connection.id + "/authorize",
        "POST",
        { generation: connection.generation },
      );
      sessionStorage.setItem("twf.mcp.connection_id", connection.id);
      window.location.assign(result.authorization_url);
    });
  }

  async function operation(
    action: "refresh" | "disconnect" | "test" | "cleanup" | "recover",
    message: string,
  ) {
    if (!connection) return;
    await run(async () => {
      const row = await mcpApi<Connection>(
        "connections/" + connection.id + "/" + action,
        "POST",
        action === "cleanup" || action === "recover"
          ? undefined
          : { generation: connection.generation },
      );
      setConnection(row);
      setNotice(message);
    });
  }

  const authorized = connection?.state === "CONNECTED" && connection.enabled;
  const ready = authorized && connection.health === "AVAILABLE";
  const registrationChanged = connection?.error === "STALE_GENERATION";

  return (
    <section aria-labelledby="provider-connections-heading">
      <h2 id="provider-connections-heading">Provider connections</h2>
      <p>
        Personal, owner-scoped connections. OAuth tokens are encrypted by the
        API and are never exposed in this page.
      </p>

      {!loaded && <p role="status">Loading provider connections…</p>}
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button disabled={pending} onClick={() => void load()}>
            Reload connection
          </button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}

      {loaded && !connection && (
        <div className="settings-integration-card">
          <h3>TradingView market evidence</h3>
          <p>
            No personal TradingView connection exists. Create one, then complete
            TradingView OAuth in your browser.
          </p>
          <button disabled={pending} onClick={createConnection}>
            Add TradingView connection
          </button>
        </div>
      )}

      {connection && (
        <div className="settings-integration-card">
          <div className="settings-integration-heading">
            <div>
              <h3>{connection.display_name}</h3>
              <p>
                State: <strong>{connection.state.replaceAll("_", " ")}</strong>{" "}
                · Health: <strong>{connection.health}</strong>
              </p>
            </div>
            <span className={ready ? "status-success" : "status-warning"}>
              {ready ? "Ready for real evidence" : "Action required"}
            </span>
          </div>
          <p>
            Generation {connection.generation} · {connection.tools.length} tools
            discovered · {connection.operations_pending} operation(s) pending
          </p>
          {connection.last_success_at && (
            <p>
              Last provider success:{" "}
              {new Date(connection.last_success_at).toLocaleString()}
            </p>
          )}
          <div className="settings-actions">
            {!authorized &&
              !registrationChanged &&
              connection.state !== "DISCONNECTING" && (
                <button disabled={pending} onClick={authorize}>
                  {connection.state === "REAUTH_REQUIRED"
                    ? "Reauthorize TradingView"
                    : "Authorize TradingView"}
                </button>
              )}
            {registrationChanged && (
              <button disabled={pending} onClick={createConnection}>
                Create replacement TradingView connection
              </button>
            )}
            {authorized && (
              <>
                <button
                  disabled={pending}
                  onClick={() =>
                    operation("test", "TradingView connection test completed.")
                  }
                >
                  Test connection
                </button>
                <button
                  disabled={pending}
                  onClick={() =>
                    operation("refresh", "TradingView authorization refreshed.")
                  }
                >
                  Refresh authorization
                </button>
              </>
            )}
            {connection.enabled && (
              <button
                disabled={pending}
                onClick={() =>
                  operation("disconnect", "TradingView disconnected.")
                }
              >
                Disconnect
              </button>
            )}
            {connection.cleanup_pending && (
              <button
                disabled={pending}
                onClick={() =>
                  operation("cleanup", "Pending credential cleanup retried.")
                }
              >
                Retry cleanup
              </button>
            )}
            {connection.recovery_required && (
              <button
                disabled={pending}
                onClick={() =>
                  operation("recover", "Connection recovery completed.")
                }
              >
                Recover connection
              </button>
            )}
            <button disabled={pending} onClick={() => void load()}>
              Reload status
            </button>
          </div>
          <p>
            Real scanning also requires the API operator setting{" "}
            <code>TWF_TRADINGVIEW_SCAN</code> to be enabled and
            contract-verified.
          </p>
        </div>
      )}
    </section>
  );
}
