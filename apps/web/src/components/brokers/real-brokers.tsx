"use client";
import Link from "next/link";
import { useState } from "react";
import { brokerProviders, providerName } from "../../lib/broker-setup";
import { brokerRoomHref } from "../../lib/broker-room-routes";
import {
  brokerAuthRequest,
  connected,
  connectionHref,
  connectionName,
  connectionState,
  manageHref,
  type Connection,
} from "../../lib/broker-connections";
import { ConnectionLoadState, useBrokerSession } from "./broker-session";
import { BrokerSetupForm, type SetupInput } from "./broker-setup-form";

export function BrokerRoster() {
  const { connections } = useBrokerSession();
  const accounts = connections?.filter(
    (value) =>
      connectionHref(value) ||
      (brokerRoomHref(
        value.account.provider_id,
        value.account.broker_account_id,
      ) &&
        value.account.enabled &&
        value.account.configured &&
        value.bound_at &&
        value.account.provider_account_id &&
        value.account.authentication_state === "REAUTH_REQUIRED"),
  );
  return (
    <section className="broker-roster">
      <ConnectionLoadState />
      {accounts?.length === 0 && (
        <div className="broker-empty-state">
          <h2>No broker connected yet.</h2>
          <p>Connect a broker to start using TWF.</p>
          <Link className="broker-primary-action" href="/brokers/manage">
            Manage Brokers
          </Link>
        </div>
      )}
      {accounts?.map((value) => (
        <Link
          className="broker-entry"
          key={value.account.broker_account_id}
          href={
            connectionHref(value) || manageHref(value.account.broker_account_id)
          }
        >
          <strong>{connectionName(value)}</strong>
          <span>{connectionState(value)} →</span>
        </Link>
      ))}
      {accounts?.length !== 0 && (
        <Link className="quiet-button" href="/brokers/manage">
          Manage Brokers
        </Link>
      )}
    </section>
  );
}

export function RealBrokers({ view = "all" }: { view?: "all" | "my" }) {
  const { connections } = useBrokerSession();
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const providers = brokerProviders.filter((provider) =>
    provider.display_name.toLowerCase().includes(query),
  );
  const accounts = connections?.filter((value) =>
    connectionName(value).toLowerCase().includes(query),
  );
  return (
    <div className="broker-room broker-content">
      <h1>Manage Brokers</h1>
      <nav className="broker-tabs" aria-label="Manage brokers">
        <Link
          href="/brokers/manage"
          aria-current={view === "all" ? "page" : undefined}
        >
          All Brokers
        </Link>
        <Link
          href="/brokers/manage/my"
          aria-current={view === "my" ? "page" : undefined}
        >
          My Brokers
        </Link>
      </nav>
      <label className="broker-search">
        Search brokers
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Broker or connection name"
        />
      </label>
      <ConnectionLoadState />
      {view === "all" ? (
        <>
          <div className="broker-provider-grid">
            {providers.map((provider) => {
              const owned =
                connections?.filter(
                  (value) => value.account.provider_id === provider.provider_id,
                ) || [];
              return (
                <article
                  className="broker-provider-card"
                  key={provider.provider_id}
                >
                  <h2>{provider.display_name}</h2>
                  <p>
                    {provider.support_state === "COMING_LATER"
                      ? "Coming later"
                      : !connections
                        ? "Checking connections…"
                        : owned.some(connected)
                          ? `Connected: ${owned.filter(connected).length}`
                          : owned.length
                            ? "Setup saved · not connected"
                            : "Not configured"}
                  </p>
                  {provider.support_state === "SUPPORTED" && (
                    <>
                      <p className="panel-intro">
                        {[
                          provider.capabilities.holdings && "Holdings",
                          provider.capabilities.positions && "Positions",
                          provider.capabilities.search && "Instruments",
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                      <div className="broker-connection-actions">
                        {owned.length > 0 && (
                          <Link
                            className="quiet-button"
                            href="/brokers/manage/my"
                          >
                            Manage
                          </Link>
                        )}
                        <Link
                          className="quiet-button"
                          href={`/brokers/manage/setup/${provider.provider_id}`}
                        >
                          {owned.length ? "Add connection" : "Setup"}
                        </Link>
                      </div>
                    </>
                  )}
                </article>
              );
            })}
          </div>
          {!providers.length && (
            <p role="status">No brokers match your search.</p>
          )}
        </>
      ) : (
        <>
          <div className="broker-provider-grid">
            {accounts?.map((value) => {
              const href = connectionHref(value);
              const setupSupported = brokerProviders.some(
                (provider) =>
                  provider.provider_id === value.account.provider_id &&
                  provider.support_state === "SUPPORTED",
              );
              return (
                <article
                  className="broker-provider-card"
                  key={value.account.broker_account_id}
                >
                  <h2>{connectionName(value)}</h2>
                  <p>{connectionState(value)}</p>
                  {!brokerRoomHref(
                    value.account.provider_id,
                    value.account.broker_account_id,
                  ) && (
                    <p className="panel-intro">
                      Workspace not available for this broker.
                    </p>
                  )}
                  <div className="broker-connection-actions">
                    {href && (
                      <Link className="quiet-button" href={href}>
                        Open
                      </Link>
                    )}
                    {setupSupported ? (
                      <Link
                        className="quiet-button"
                        href={manageHref(value.account.broker_account_id)}
                      >
                        {value.account.authentication_state ===
                        "REAUTH_REQUIRED"
                          ? "Reconnect"
                          : "Manage"}
                      </Link>
                    ) : (
                      <p>Setup and management are not available yet.</p>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
          {accounts?.length === 0 && (
            <p role="status">
              {query
                ? "No connections match your search."
                : "No saved connections yet."}{" "}
              <Link href="/brokers/manage">Find a broker</Link>
            </p>
          )}
        </>
      )}
    </div>
  );
}

export function BrokerSetup({
  providerId,
  accountId,
}: {
  providerId?: string;
  accountId?: string;
}) {
  const { connections, reload } = useBrokerSession();
  const [createdId, setCreatedId] = useState<string | undefined>(accountId);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const value = connections?.find(
    (connection) => connection.account.broker_account_id === createdId,
  );
  const roomHref = value ? connectionHref(value) : null;
  const manifest = brokerProviders.find(
    (provider) =>
      provider.provider_id === (value?.account.provider_id || providerId),
  );
  async function save(input: SetupInput) {
    // Only the accepted configuration contract may persist inputs. Other manifests need a supported backend strategy, never a generic credential dump.
    if (
      manifest?.provider_id !== "zerodha" ||
      manifest.auth_strategy !== "BROWSER_REDIRECT_CALLBACK" ||
      Object.keys(input.credentials).sort().join() !== "api_key,api_secret"
    )
      throw new Error("Unsupported configuration");
    setMessage("");
    let account = value?.account;
    if (!account) {
      account = (await brokerAuthRequest("create-account", {
        provider_id: manifest.provider_id,
        label: input.label,
      })) as Connection["account"];
      await reload();
      setCreatedId(account.broker_account_id);
    }
    try {
      await brokerAuthRequest(
        `accounts/${account.broker_account_id}/configure`,
        {
          api_key: input.credentials.api_key,
          api_secret: input.credentials.api_secret,
          expected_revision: account.configuration_revision,
          expected_generation: account.connection_generation,
        },
      );
      setEditing(false);
      setMessage("Configuration saved. Connect to verify your account.");
    } finally {
      await reload();
    }
  }
  async function action(name: "connect" | "disconnect" | "cleanup") {
    if (!value) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await brokerAuthRequest(
        `accounts/${value.account.broker_account_id}/${name}`,
        name === "disconnect"
          ? { expected_generation: value.account.connection_generation }
          : {},
      );
      if (name === "connect") {
        // Auth mechanics remain in the backend. Only the accepted external login destination is navigable.
        const target = new URL(result.login_url);
        if (
          value.account.provider_id !== "zerodha" ||
          target.origin !== "https://kite.zerodha.com" ||
          target.pathname !== "/connect/login" ||
          target.username ||
          target.password
        )
          throw new Error("Invalid destination");
        window.location.assign(target.href);
      } else {
        setMessage(
          name === "disconnect"
            ? "Disconnected from TWF. Your broker session may remain valid until expiry or logout at the broker."
            : "Cleanup retried.",
        );
        await reload();
      }
    } catch {
      setMessage("Could not update the connection. Refresh and try again.");
    } finally {
      setBusy(false);
    }
  }
  if (!connections)
    return (
      <div className="broker-room">
        <h1>Broker setup</h1>
        <ConnectionLoadState />
      </div>
    );
  if (
    (createdId && !value) ||
    !manifest ||
    manifest.support_state !== "SUPPORTED"
  )
    return (
      <div className="broker-room">
        <h1>Broker setup unavailable</h1>
        <Link href="/brokers/manage">Manage Brokers</Link>
      </div>
    );
  return (
    <div className="broker-room broker-content broker-setup">
      <Link href="/brokers/manage/my">← My Brokers</Link>
      <h1>
        {value?.account.configured
          ? connectionName(value)
          : `Setup ${manifest.display_name}`}
      </h1>
      {value && <p>{connectionState(value)}</p>}
      {message && <p role="status">{message}</p>}
      {value?.account.provider_account_id && (
        <p>
          Verified account: <strong>{value.account.provider_account_id}</strong>
        </p>
      )}
      {value?.callback_url && (
        <p className="broker-account-id">
          Set this redirect URL in your broker app:{" "}
          <code>{value.callback_url}</code>
        </p>
      )}
      {(!value?.account.configured || editing) &&
      (!value || value.can_configure) ? (
        <>
          <p className="panel-intro">
            Save your app details, then continue securely at{" "}
            {manifest.display_name}.
            {value?.account.configured
              ? " Updating credentials requires a fresh connection."
              : ""}
          </p>
          <BrokerSetupForm
            manifest={manifest}
            label={value?.account.label}
            lockedLabel={!!value}
            onSubmit={save}
          />
          {editing && (
            <button className="quiet-button" onClick={() => setEditing(false)}>
              Cancel
            </button>
          )}
        </>
      ) : (
        value?.can_configure && (
          <button className="quiet-button" onClick={() => setEditing(true)}>
            Update credentials
          </button>
        )
      )}
      {value && (
        <div className="broker-connection-actions">
          {value.can_connect && (
            <button
              className="quiet-button"
              disabled={busy}
              onClick={() => void action("connect")}
            >
              {value.account.authentication_state === "REAUTH_REQUIRED"
                ? "Reconnect"
                : `Connect ${providerName(value.account.provider_id)}`}
            </button>
          )}
          {roomHref && (
            <Link className="quiet-button" href={roomHref}>
              Open connection
            </Link>
          )}
          {value.can_disconnect && value.account.configured && (
            <button
              className="quiet-button"
              disabled={busy}
              onClick={() => void action("disconnect")}
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
              Retry credential cleanup
            </button>
          )}
        </div>
      )}
      {value?.unavailable_reason && (
        <p className="panel-intro">{value.unavailable_reason}</p>
      )}
    </div>
  );
}
