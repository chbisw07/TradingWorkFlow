import type { TWFOrder } from "./twf-orders";

export type TWFQueueEntry = {
  queue_entry_id: string;
  twf_order_id: string;
  owner_id: string;
  queue_state: "READY" | "HELD";
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
  event_type: "QUEUE_ADMITTED" | "QUEUE_HELD" | "QUEUE_RELEASED";
  from_state: "READY" | "HELD" | null;
  to_state: "READY" | "HELD";
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
