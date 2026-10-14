import type { Side } from "./broker-orders";

export type TWFOrderInput = {
  account_id: string;
  reference: string;
  native_token: string;
  side: Side;
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  limit_price: string | null;
  product: "MIS" | "CNC" | "NRML";
  validity: "DAY" | "IOC";
  notes: string;
};

export type TWFInstrument = {
  asset_class: "EQUITY" | "FUTURES" | "OPTION";
  instrument_id: string;
  exchange: string;
  symbol: string;
  underlying_id: string | null;
  expiry: string | null;
  strike: string | null;
  option_type: "CE" | "PE" | null;
  lot_size: number | null;
  tick_size: string | null;
};

export type TWFTerms = {
  side: Side;
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  limit_price: string | null;
  product: "INTRADAY" | "DELIVERY" | "CARRY_FORWARD";
  validity: "DAY" | "IOC";
};

export type TWFPreview = {
  preview_id: string;
  expires_at: string;
  instrument: TWFInstrument;
  terms: TWFTerms;
  source: "MANUAL";
  account_id: string;
};

export type TWFOrder = {
  twf_order_id: string;
  owner_id: string;
  instrument: TWFInstrument;
  terms: TWFTerms;
  provenance: {
    source: "MANUAL";
    source_ref: string | null;
    references: Record<string, string>;
  };
  state: string;
  state_reason_code: string | null;
  state_reason: string | null;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  notes: string;
};

export type TWFEvent = {
  event_id: string;
  sequence: number;
  event_type: string;
  from_state: string | null;
  to_state: string | null;
  actor: string;
  authority: string;
  reason_code: string | null;
  reason: string | null;
  details: Record<string, unknown>;
  occurred_at: string;
};

export type TWFCreation = {
  order: TWFOrder;
  validation: {
    ready: boolean;
    violations: string[];
    order_version: number | null;
  };
};

export class TWFOrderApiError extends Error {
  constructor(
    message: string,
    public code: string,
  ) {
    super(message);
  }
}

export async function twfOrdersApi<T>(path = "", body?: unknown): Promise<T> {
  const response = await fetch(
    "/api/v1/twf-orders" + (path ? "/" + path : ""),
    {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    },
  );
  const data = await response.json();
  if (!response.ok)
    throw new TWFOrderApiError(
      data?.error?.message || "TWF Orders request failed. Please retry.",
      data?.error?.code || "REQUEST_FAILED",
    );
  return data as T;
}
