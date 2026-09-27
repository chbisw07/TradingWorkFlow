import { providerName } from "./broker-setup";
import { brokerRoomHref } from "./broker-room-routes";
export type Connection = {
  account: {
    broker_account_id: string;
    provider_id: string;
    label: string;
    enabled: boolean;
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
  bound_at: string | null;
};
export const connected = (value: Connection) =>
  Boolean(
    value.account.enabled &&
    value.account.configured &&
    value.bound_at &&
    value.account.provider_account_id &&
    value.account.authentication_state === "CONNECTED",
  );
export const connectionName = (value: Connection) =>
  `${providerName(value.account.provider_id)} · ${value.account.label}`;
export const connectionHref = (value: Connection) =>
  connected(value)
    ? brokerRoomHref(value.account.provider_id, value.account.broker_account_id)
    : null;
export const manageHref = (id: string) => `/brokers/manage/accounts/${id}`;
export function connectionState(value: Connection) {
  if (!value.account.enabled) return "Disabled";
  switch (value.account.authentication_state) {
    case "CONNECTED":
      return connected(value) ? "Connected" : "Not connected";
    case "REAUTH_REQUIRED":
      return "Reconnect required";
    case "AUTHENTICATING":
    case "AUTH_IN_PROGRESS":
      return "Connecting";
    case "ERROR":
      return "Connection unavailable";
    default:
      return value.account.configured ? "Not connected" : "Setup incomplete";
  }
}
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
          : "Broker connection unavailable. Check setup and try again.",
    );
  return response.json();
}
