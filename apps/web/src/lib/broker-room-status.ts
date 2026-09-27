import type { NativeDataset, Portfolio, RoomView } from "./portfolio";
import { connected, type Connection } from "./broker-connections";

export function datasetStale(data: NativeDataset, now: number) {
  const meta = data.metadata;
  return (
    meta.freshness === "STALE" ||
    (data.rows !== null &&
      meta.received_at !== null &&
      now - Date.parse(meta.received_at) > meta.freshness_policy_seconds * 1000)
  );
}

/** Authentication takes precedence; a connection alone never proves a healthy read. */
export function brokerRoomHeadline({
  connection,
  datasets,
  now,
  failed = false,
  referenceOnly = false,
}: {
  connection: string | undefined;
  datasets: NativeDataset[] | null;
  now: number;
  failed?: boolean;
  referenceOnly?: boolean;
}) {
  if (connection === "REAUTH_REQUIRED") return "REAUTH REQUIRED";
  if (connection === "AUTH_IN_PROGRESS" || connection === "AUTHENTICATING")
    return "CONNECTING";
  if (
    ["NOT_CONFIGURED", "DISCONNECTED", "AUTH_REQUIRED"].includes(
      connection || "",
    )
  )
    return "NOT CONNECTED";
  if (failed || connection === "ERROR") return "READ ONLY · UNAVAILABLE";
  if (!connection) return "READ ONLY · CHECKING CONNECTION";
  if (connection !== "CONNECTED") return "READ ONLY · UNAVAILABLE";
  // Instruments are reference data; opening them must not trigger portfolio reads
  // or turn an authentication/read-health flag into a live observation claim.
  if (referenceOnly) return "READ ONLY · REFERENCE DATA";
  if (!datasets) return "READ ONLY · LOADING DATA";
  if (datasets.every((data) => data.rows === null))
    return "READ ONLY · UNAVAILABLE";
  if (datasets.some((data) => datasetStale(data, now)))
    return "READ ONLY · STALE DATA";
  const healthy =
    datasets.length > 0 &&
    datasets.every((data) => {
      const meta = data.metadata;
      const received = meta.received_at ? Date.parse(meta.received_at) : NaN;
      return (
        data.rows !== null &&
        meta.health === "AVAILABLE" &&
        meta.completeness === "COMPLETE" &&
        meta.freshness === "FRESH" &&
        !meta.failure_code &&
        Number.isFinite(received) &&
        received <= now &&
        meta.freshness_policy_seconds > 0
      );
    });
  return healthy ? "LIVE DATA · READ ONLY" : "READ ONLY · DEGRADED";
}

export type RoomObservation = { value: Portfolio; startedAt: number };

/** Reconcile only this account. A refresh received during a read fences that read's auth claim. */
export function effectiveBrokerRoomState({
  accountId,
  connections,
  sessionObservedAt,
  sessionError,
  observation,
  view,
  now,
  readError,
}: {
  accountId: string;
  connections: Connection[] | null;
  sessionObservedAt: number;
  sessionError: string;
  observation: RoomObservation | null;
  view: RoomView;
  now: number;
  readError: string;
}) {
  const current = connections?.find(
    (item) => item.account.broker_account_id === accountId,
  );
  const account = current?.account;
  const supported = account?.provider_id === "zerodha";
  const data = observation?.value;
  const datasets = data
    ? view === "dashboard"
      ? [data.holdings, data.positions]
      : view === "instruments"
        ? null
        : [data[view]]
    : null;
  const generationsMatch =
    !!account &&
    !!datasets &&
    datasets.every(
      (dataset) =>
        dataset.metadata.connection_generation ===
        account.connection_generation,
    );
  let connection = account?.authentication_state;
  if (sessionError || (connections !== null && (!current || !supported)))
    connection = "UNAVAILABLE";
  else if (
    account &&
    (!account.enabled || (connection === "CONNECTED" && !connected(current!)))
  )
    connection = "DISCONNECTED";
  else if (
    account &&
    data &&
    observation &&
    datasets &&
    generationsMatch &&
    sessionObservedAt < observation.startedAt &&
    connection === "CONNECTED"
  ) {
    // A read may discover expired authentication after the last session refresh.
    // Later session refreshes and different generations always override it.
    connection = data.connection_state;
  }
  const obsoleteRead = !!data && view !== "instruments" && !generationsMatch;
  let headline = brokerRoomHeadline({
    connection,
    datasets,
    now,
    failed: !!readError || !!sessionError,
    referenceOnly: view === "instruments",
  });
  if (connection === "CONNECTED" && !readError && view !== "instruments") {
    if (obsoleteRead) headline = "READ ONLY · STALE DATA";
    // UNKNOWN is the account foundation default, not a failed observation.
    else if (
      headline === "LIVE DATA · READ ONLY" &&
      ["DEGRADED", "UNAVAILABLE"].includes(account?.read_health || "")
    )
      headline =
        account?.read_health === "UNAVAILABLE"
          ? "READ ONLY · UNAVAILABLE"
          : "READ ONLY · DEGRADED";
  }
  const retained =
    !!datasets?.some((dataset) => dataset.rows !== null) &&
    (connection !== "CONNECTED" || obsoleteRead);
  const actionLabel = !supported
    ? null
    : connection === "REAUTH_REQUIRED"
      ? "Reconnect"
      : connection === "DISCONNECTED" ||
          connection === "AUTH_REQUIRED" ||
          connection === "NOT_CONFIGURED"
        ? "Configure / Connect"
        : "Manage connection";
  return { connection, headline, retained, actionLabel, label: account?.label };
}
