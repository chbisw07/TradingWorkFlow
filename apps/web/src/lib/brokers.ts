export type BrokerView =
  "dashboard" | "holdings" | "positions" | "orders" | "funds";
export const brokerViews: BrokerView[] = [
  "dashboard",
  "holdings",
  "positions",
  "orders",
  "funds",
];
export type Observation = {
  source: string;
  broker_account_id: string;
  source_as_of: string | null;
  fetched_at: string;
  health: string;
  freshness: "FRESH" | "STALE" | "UNKNOWN";
  completeness: "COMPLETE" | "PARTIAL" | "MISSING";
  revision: string;
  freshness_policy_seconds: number;
};
export type Instrument = {
  canonical_id: string | null;
  exchange: string;
  broker_symbol: string;
  native_id: string;
  currency: string;
  quantity_unit: string;
};
export type Holding = {
  instrument: Instrument;
  quantity: string;
  average_cost: string;
  last_price: string;
  current_value: string;
  pnl: string;
  pnl_percent: string | null;
};
export type Position = {
  instrument: Instrument;
  product: string;
  quantity: string;
  average_price: string;
  last_price: string;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  broker_state: string;
};
export type Order = {
  broker_order_id: string;
  instrument: Instrument;
  side: string;
  quantity: string;
  filled_quantity: string;
  remaining_quantity: string;
  price: string | null;
  status: string;
  observed_at: string;
  reason: string | null;
};
export type Funds = {
  currency: string;
  available_cash: string | null;
  used_margin: string | null;
  collateral: string | null;
};
export type Dataset<T> = { metadata: Observation; rows: T[] | null };
export type Snapshot = {
  contract_version: "broker.read.v1";
  request_id: string;
  account: {
    broker_account_id: string;
    provider_id: string;
    owner_user_id: string;
    label: string;
    mode: "SYNTHETIC" | "SANDBOX" | "LIVE";
  };
  operation: { connection: string; read: string; error: string | null };
  holdings: Dataset<Holding>;
  positions: Dataset<Position>;
  orders: Dataset<Order>;
  funds: { metadata: Observation; values: Funds | null };
};
export type Overview = {
  contract_version: "broker.read.v1";
  scenario_time: string;
  providers: { provider_id: string; name: string }[];
  accounts: Snapshot[];
  position_aggregates: {
    canonical_id: string;
    exchange: string;
    product: string;
    currency: string;
    quantity_unit: string;
    quantity: string;
    qualified: boolean;
    contributions: {
      broker_account_id: string;
      quantity: string;
      metadata: Observation;
    }[];
  }[];
  unmapped_position_count: number;
  missing_position_accounts: number;
};
