import type { TWFOrder } from "./twf-orders";

export type QueuePolicy = {
  broker_account_id: string;
  current_dispatch_mode: "MANUAL" | "AUTO";
  version: number;
  updated_at: string;
  execution_enabled: boolean;
};
export type QueueState =
  | "READY"
  | "HELD"
  | "DISPATCHING"
  | "DISPATCHED"
  | "FAILED"
  | "RECONCILIATION_REQUIRED"
  | "CANCELLED";
export type TWFQueueEntry = {
  effective_dispatch_mode?: "MANUAL" | "AUTO";
  broker_account_id?: string | null;
  source_kind?: string;
  source_reference?: string | null;
  public_order_id?: string | null;
  public_queue_id?: string | null;
  queue_entry_id: string;
  twf_order_id: string;
  owner_id: string;
  queue_state: QueueState;
  version: number;
  admitted_at: string;
  updated_at: string;
  created_by: string;
  reason_code: string | null;
  reason_message: string | null;
  order: TWFOrder;
};

export type TWFQueuePage = {
  items: TWFQueueEntry[];
  next_cursor: string | null;
  has_more: boolean;
};

export type TWFQueueEvent = {
  event_id: string;
  queue_entry_id: string;
  twf_order_id: string;
  sequence: number;
  queue_version: number;
  event_type: string;
  details?: Record<string, unknown>;
  from_state: QueueState | null;
  to_state: QueueState;
  actor: string;
  reason_code: string | null;
  reason_message: string | null;
  occurred_at: string;
};

export class TWFQueueApiError extends Error {
  constructor(
    message: string,
    public code: string,
  ) {
    super(message);
  }
}

export async function twfQueueApi<T>(path = "", body?: unknown): Promise<T> {
  const response = await fetch(
    "/api/v1/twf-queue" +
      (path ? (path.startsWith("?") ? path : "/" + path) : ""),
    {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    },
  );
  const data = await response.json();
  if (!response.ok)
    throw new TWFQueueApiError(
      data?.error?.message || "TWF Queue request failed. Please retry.",
      data?.error?.code || "REQUEST_FAILED",
    );
  return data as T;
}
