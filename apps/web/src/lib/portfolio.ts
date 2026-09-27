export type NativeInstrument = {
  native_id: string;
  symbol: string;
  exchange: string;
  canonical_id: string | null;
  catalog_version: string | null;
  catalog_state: string;
  name: string | null;
  segment: string | null;
  instrument_type: string | null;
  expiry: string | null;
  strike: string | null;
  derivative_kind: string | null;
  lot_size: number | null;
  tick_size: string | null;
};
export type NativeRow = {
  instrument: NativeInstrument;
  product: string;
  product_known: boolean;
  quantity: string;
  average_price: string | null;
  last_price: string | null;
  close_price: string | null;
  pnl: string | null;
  current_value: string | null;
  pnl_percent: string | null;
  used_quantity: string | null;
  available_quantity: string | null;
  unsettled_quantity: string | null;
  settled_quantity: string | null;
  authorised_quantity: string | null;
  collateral_quantity: string | null;
  collateral_type: string | null;
  financed_quantity: string | null;
  financed_value: string | null;
  day_change: string | null;
  day_change_percent: string | null;
  overnight_quantity: string | null;
  buy_quantity: string | null;
  sell_quantity: string | null;
  buy_average: string | null;
  sell_average: string | null;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  multiplier: string | null;
};
export type NativeDataset = {
  metadata: {
    source: string;
    source_as_of: string | null;
    attempted_at: string;
    received_at: string | null;
    freshness: string;
    freshness_policy_seconds: number;
    health: string;
    completeness: string;
    failure_code: string | null;
    connection_generation: number;
    rejected_rows: number;
    total_rows: number | null;
  };
  rows: NativeRow[] | null;
  activity_rows: NativeRow[] | null;
};
export type Portfolio = {
  broker_account_id: string;
  provider_id: string;
  account_label: string;
  connection_state: string;
  holdings: NativeDataset;
  positions: NativeDataset;
  summary: {
    holdings_count: number | null;
    holdings_value: string | null;
    open_positions_count: number | null;
    realized_pnl: string | null;
    unrealized_pnl: string | null;
    position_pnl: string | null;
  };
};
export const roomViews = [
  "dashboard",
  "holdings",
  "positions",
  "instruments",
] as const;
export type RoomView = (typeof roomViews)[number];
