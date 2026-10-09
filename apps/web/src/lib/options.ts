/** Shared canonical O2 contracts. Decimal values are JSON strings; no broker tokens. */
import type { Draft, Intent } from "./broker-orders";

export type OptionContract = NonNullable<Intent["option_contract"]>;
export type OptionContractRequest = Pick<
  OptionContract,
  "exchange" | "underlying_symbol" | "expiry" | "strike" | "option_type"
>;
export type OptionChainRequest = {
  underlying: string;
  expiry: string;
  around_atm?: number;
  strike_min?: string;
  strike_max?: string;
  side?: "CE" | "PE";
};
export type OptionChainCapabilities = {
  provider: string;
} & Record<
  | "contracts"
  | "quotes"
  | "bid_ask"
  | "volume"
  | "open_interest"
  | "oi_change"
  | "iv"
  | "greeks",
  "SUPPORTED" | "PARTIAL" | "UNSUPPORTED"
>;
export type OptionMarketSnapshot = Record<
  | "ltp"
  | "bid"
  | "ask"
  | "bid_quantity"
  | "ask_quantity"
  | "spread"
  | "spread_percent"
  | "volume"
  | "open_interest"
  | "previous_open_interest"
  | "change_in_open_interest"
  | "implied_volatility"
  | "delta"
  | "gamma"
  | "theta"
  | "vega"
  | "source_time",
  string | null
>;
export type OptionLegSnapshot = {
  contract: OptionContract;
  moneyness: "ITM" | "ATM" | "OTM" | null;
  market: OptionMarketSnapshot;
  availability: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE";
  warnings: string[];
};
export type OptionChainRow = {
  strike: string;
  is_atm: boolean | null;
  distance_from_spot: string | null;
  distance_percent: string | null;
  ce: OptionLegSnapshot | null;
  pe: OptionLegSnapshot | null;
};
export type OptionChainProvenance = {
  provider: string;
  contract_source: string;
  market_source: string;
  master_received_at: string;
  received_at: string;
  source_time: string | null;
  freshness: "FRESH" | "STALE" | "SOURCE_TIME_UNAVAILABLE" | "UNAVAILABLE";
  quote_ttl_seconds: number;
  cached: boolean;
  oi_unit: string;
  iv_unit: string;
};
export type OptionChainSnapshot = {
  underlying: string;
  spot: string | null;
  expiry: string;
  dte: number;
  as_of: string;
  atm_strike: string | null;
  rows: OptionChainRow[];
  status: "COMPLETE" | "PARTIAL";
  capabilities: OptionChainCapabilities;
  provenance: OptionChainProvenance;
  warnings: string[];
  missing_capabilities: string[];
};
export type CanonicalOptionPreview = {
  contract: OptionContractRequest;
  order: Omit<Draft, "reference" | "native_token">;
};
