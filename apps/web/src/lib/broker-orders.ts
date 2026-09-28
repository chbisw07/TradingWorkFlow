import type { Instrument } from "./brokers";
export type Side = "BUY" | "SELL";
export type Capability = {
  enabled: boolean;
  products: string[];
  order_types: {
    name: string;
    price_required: boolean;
    trigger_required: boolean;
    validities: string[];
  }[];
  instrument: Instrument | null;
  quantity_unit: "shares" | "lots";
  max_quantity: number;
};
export type Choices = {
  underlyings: string[];
  expiries: string[];
  option_types: string[];
  strikes: string[];
  instruments: Instrument[];
  total: number;
  page: number;
};
export type Draft = {
  reference: string;
  native_token: string;
  side: Side;
  product: string;
  order_type: string;
  quantity: number;
  lots: number | null;
  price?: string;
  trigger_price: string | null;
  validity: string;
};
export type Intent = {
  id: string;
  account_id: string;
  account_name: string;
  instrument: Instrument;
  order: Draft;
  status:
    | "PREVIEWED"
    | "SUBMITTING"
    | "SUBMITTED"
    | "BROKER_REJECTED"
    | "SUBMISSION_UNKNOWN";
  expires_at: string;
  created_at: string;
  broker_order_id: string | null;
  provider_status: string | null;
  failure: string | null;
  estimated_value: string;
  estimated_margin: string | null;
  available_cash: string | null;
};
export const money = (value: string | number | null | undefined) =>
  value == null || value === ""
    ? "—"
    : `₹ ${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
// Presentation eligibility only; the server resolves and validates again before dispatch.
export function canOrder(i: Instrument) {
  const lot = Number(i.lot_size);
  if (
    !i.native_token ||
    !(Number(i.tick_size) > 0) ||
    !Number.isInteger(lot) ||
    lot <= 0
  )
    return false;
  if (i.kind === "EQ")
    return (
      ["NSE", "BSE"].includes(i.exchange) &&
      i.segment === i.exchange &&
      lot === 1
    );
  // India has a fixed UTC+05:30 offset; compare catalog ISO dates in exchange time.
  const today = new Date(Date.now() + 330 * 60_000).toISOString().slice(0, 10);
  return (
    i.exchange === "NFO" &&
    ["FUT", "CE", "PE"].includes(i.kind || "") &&
    i.segment === (i.kind === "FUT" ? "NFO-FUT" : "NFO-OPT") &&
    !!i.underlying &&
    !!i.expiry &&
    i.expiry >= today &&
    (i.kind === "FUT" || Number(i.strike) > 0)
  );
}
