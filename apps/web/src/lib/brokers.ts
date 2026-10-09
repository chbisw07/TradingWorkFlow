export type Account = {
  id: string;
  provider: string;
  name: string;
  identity: string | null;
  state:
    | "configured"
    | "connecting"
    | "connected"
    | "reauth_required"
    | "disconnected";
  health: "unknown" | "healthy" | "degraded";
  generation: number;
  updated_at: string;
  last_read_at: string | null;
};
export type Provider = { id: string; name: string; supported: boolean };
export type Instrument = {
  symbol: string;
  exchange: string;
  reference: string;
  native_token: string | null;
  name?: string | null;
  underlying?: string | null;
  expiry?: string | null;
  strike?: string | null;
  kind?: string | null;
  segment?: string | null;
  lot_size?: string | null;
  tick_size?: string | null;
  canonical_id?: string | null;
  underlying_type?: "INDEX" | "EQUITY" | "UNKNOWN" | null;
  option_type?: "CE" | "PE" | null;
  currency?: string | null;
  is_active?: boolean | null;
  last_trading_date?: string | null;
  freeze_quantity?: number | null;
  contract_multiplier?: string | null;
};
export type Row = Record<string, string | number | boolean | null | Instrument>;
export type Snapshot = {
  account: Account;
  fetched_at: string;
  data:
    | Row[]
    | Record<string, number | string | null>
    | {
        items: Instrument[];
        total: number;
        page: number;
        limit: number;
        fetched_at: string;
      };
};
export const functions = [
  "overview",
  "holdings",
  "positions",
  "orders",
  "funds",
  "instruments",
] as const;
export type BrokerFunction = (typeof functions)[number];
export const title = (value: string) =>
  value.charAt(0).toUpperCase() + value.slice(1);
export const stateLabel = (a: Account) =>
  ({
    configured: "Not connected",
    connected: "Connected",
    connecting: "Connecting",
    reauth_required: "Re-authentication required",
    disconnected: "Not connected",
  })[a.state];
export const operational = (a: Account) =>
  !!a.identity && !["configured", "disconnected"].includes(a.state);
export function newer(a: Account, b?: Account): Account {
  return !b ||
    a.generation > b.generation ||
    (a.generation === b.generation && a.updated_at >= b.updated_at)
    ? a
    : b;
}
export function readLabel(
  account: Account,
  snapshot: Snapshot | null,
  failed: boolean,
  now: number,
) {
  if (account.state === "reauth_required") return "REAUTH REQUIRED";
  if (account.state === "connecting") return "CONNECTING";
  if (account.state !== "connected") return "NOT CONNECTED";
  if (failed || account.health === "degraded") return "READ ONLY · DEGRADED";
  if (!snapshot || snapshot.account.generation !== account.generation)
    return "READ ONLY · AWAITING DATA";
  if (now - Date.parse(snapshot.fetched_at) > 30_000)
    return "READ ONLY · STALE DATA";
  return "LIVE DATA · READ ONLY";
}
export async function brokerApi<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api/v1/brokers/" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data?.error?.message || "Broker request failed. Please retry.",
    );
  return data as T;
}
