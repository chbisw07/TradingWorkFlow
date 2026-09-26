"use client";

import { useEffect, useState, type FormEvent } from "react";

type Connection = {
  account: {
    broker_account_id: string;
    label: string;
    configured: boolean;
    authentication_state: string;
    provider_account_id: string | null;
    connection_generation: number;
    configuration_revision: number;
    read_health: string;
  };
  can_configure: boolean;
  can_connect: boolean;
  can_disconnect: boolean;
  unavailable_reason: string | null;
  callback_url: string;
  cleanup_pending: number;
};

export async function brokerAuthRequest(path: string, body?: object) {
  const response = await fetch(`/api/v1/broker-auth/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? "Your session expired. Sign in again."
        : response.status === 409
          ? "Connection changed or verification failed. Refresh and retry."
          : "Broker authentication unavailable. Check setup and try again.",
    );
  return response.json();
}

function ConnectionCard({
  value,
  reload,
}: {
  value: Connection;
  reload: () => Promise<void>;
}) {
  const { account } = value;
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function action(name: string, body: object = {}) {
    setBusy(true);
    setMessage("");
    try {
      const result = await brokerAuthRequest(
        `accounts/${account.broker_account_id}/${name}`,
        body,
      );
      if (name === "connect") {
        const target = new URL(result.login_url);
        if (
          target.origin !== "https://kite.zerodha.com" ||
          target.pathname !== "/connect/login"
        )
          throw new Error("Invalid broker login destination.");
        window.location.assign(target.href);
      } else {
        setMessage(
          name === "disconnect"
            ? "Disconnected from TWF. Your Zerodha session may remain valid until expiry or logout at Zerodha."
            : "Saved. No secret is displayed or retained in this form.",
        );
        await reload();
      }
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const body = {
      api_key: data.get("api_key"),
      api_secret: data.get("api_secret"),
      expected_revision: account.configuration_revision,
      expected_generation: account.connection_generation,
    };
    form.reset();
    void action("configure", body);
  }
  const state = account.authentication_state.replaceAll("_", " ");
  return (
    <article
      className="broker-real-card"
      aria-label={`${account.label} connection`}
    >
      <div className="broker-room-heading">
        <div>
          <p className="eyebrow">ZERODHA / PERSONAL ACCOUNT</p>
          <h3>{account.label}</h3>
        </div>
        <span className="broker-mode">LIVE DATA · READ ONLY</span>
      </div>
      <p className="broker-safety-label">TRADING DISABLED</p>
      <p role="status">
        <strong>{state}</strong> ·{" "}
        {account.configured ? "Configured" : "Not configured"}
      </p>
      {account.provider_account_id && (
        <p>
          Verified provider account:{" "}
          <strong>{account.provider_account_id}</strong>
        </p>
      )}
      <p className="panel-intro">
        Authentication and identity only. Real holdings, positions, orders and
        funds are not available yet. Read health: {account.read_health}.
      </p>
      {value.can_configure && (
        <details>
          <summary>Configure Zerodha</summary>
          <p className="broker-account-id">
            Register this callback with your Kite app: {value.callback_url}
          </p>
          <form className="broker-credential-form" onSubmit={save}>
            <label>
              API key / app identifier
              <input
                name="api_key"
                autoComplete="off"
                required
                maxLength={128}
                pattern="[A-Za-z0-9_-]+"
              />
            </label>
            <label>
              API secret
              <input
                name="api_secret"
                type="password"
                autoComplete="new-password"
                required
                maxLength={4096}
              />
            </label>
            <p className="panel-intro">
              Saving replaces the stored credentials and requires a fresh
              connection.
            </p>
            <button className="quiet-button" disabled={busy} type="submit">
              Save configuration
            </button>
          </form>
        </details>
      )}
      <div className="broker-connection-actions">
        <button
          className="quiet-button"
          disabled={busy || !value.can_connect}
          onClick={() => void action("connect")}
        >
          {account.authentication_state === "REAUTH_REQUIRED"
            ? "Reauthenticate with Zerodha"
            : "Connect Zerodha"}
        </button>
        {value.can_disconnect && account.configured && (
          <button
            className="quiet-button"
            disabled={busy}
            onClick={() =>
              void action("disconnect", {
                expected_generation: account.connection_generation,
              })
            }
          >
            Disconnect from TWF
          </button>
        )}
        {value.cleanup_pending > 0 && (
          <button
            className="quiet-button"
            disabled={busy}
            onClick={() => void action("cleanup")}
          >
            Retry secret cleanup ({value.cleanup_pending})
          </button>
        )}
      </div>
      {value.unavailable_reason && (
        <p className="panel-intro">{value.unavailable_reason}</p>
      )}
      {message && <p role="status">{message}</p>}
    </article>
  );
}

export function RealBrokers() {
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function reload() {
    setConnections(await brokerAuthRequest("accounts"));
  }
  useEffect(() => {
    let active = true;
    brokerAuthRequest("accounts")
      .then((data) => {
        if (active) setConnections(data);
      })
      .catch(() => {
        if (active) setError("Real broker setup is temporarily unavailable.");
      });
    return () => {
      active = false;
    };
  }, []);
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = event.currentTarget;
    try {
      await brokerAuthRequest("create-account", {
        provider_id: "zerodha",
        label: new FormData(form).get("label"),
      });
      form.reset();
      await reload();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      id="real-brokers"
      className="broker-real"
      aria-labelledby="real-brokers-title"
    >
      <div className="broker-room-heading">
        <div>
          <p className="eyebrow">REAL BROKERS</p>
          <h2 id="real-brokers-title">Zerodha connection</h2>
        </div>
        <span className="broker-mode">TRADING DISABLED</span>
      </div>
      <p className="panel-intro">
        Connect your own Kite account for verified, read-only access. Portfolio
        views arrive in a later milestone.
      </p>
      {connections?.map((value) => (
        <ConnectionCard
          key={value.account.broker_account_id}
          value={value}
          reload={reload}
        />
      ))}
      {connections && (
        <form onSubmit={add} className="broker-add-account">
          <label>
            Account label
            <input
              name="label"
              required
              minLength={1}
              maxLength={80}
              defaultValue="My Zerodha"
            />
          </label>
          <button className="quiet-button" disabled={busy}>
            Add Zerodha account
          </button>
        </form>
      )}
      {!connections && !error && (
        <p role="status">Loading real broker setup…</p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
