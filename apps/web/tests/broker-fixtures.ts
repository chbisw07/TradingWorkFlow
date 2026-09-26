import type { Overview, Snapshot } from "../src/lib/brokers";
export function brokerFixture(): Overview {
  const account = {
    broker_account_id: "00000000-0000-4000-8000-000000000001",
    provider_id: "synthetic-alpha",
    owner_user_id: "owner",
    label: "Alpha A1",
    mode: "SYNTHETIC" as const,
  };
  const meta = {
    source: account.provider_id,
    broker_account_id: account.broker_account_id,
    source_as_of: "2026-09-26T12:00:00Z",
    fetched_at: "2026-09-26T12:00:00Z",
    health: "AVAILABLE",
    freshness: "FRESH" as const,
    completeness: "COMPLETE" as const,
    revision: "bw1-fixture.v1",
    freshness_policy_seconds: 60,
  };
  const instrument = {
    canonical_id: "NSE:HAL",
    exchange: "NSE",
    broker_symbol: "HAL-EQ",
    native_id: "alpha-1001",
    currency: "INR",
    quantity_unit: "SHARES",
  };
  const room: Snapshot = {
    contract_version: "broker.read.v1",
    request_id: "test",
    account,
    operation: { connection: "CONNECTED", read: "AVAILABLE", error: null },
    holdings: {
      metadata: meta,
      rows: [
        {
          instrument,
          quantity: "10",
          average_cost: "4000",
          last_price: "4100",
          current_value: "41000",
          pnl: "1000",
          pnl_percent: "2.5",
        },
      ],
    },
    positions: {
      metadata: meta,
      rows: [
        {
          instrument,
          product: "INTRADAY",
          quantity: "100",
          average_price: "4000",
          last_price: "4100",
          realized_pnl: "0",
          unrealized_pnl: "10000",
          broker_state: "NET",
        },
      ],
    },
    orders: {
      metadata: meta,
      rows: [
        {
          broker_order_id: "observed-1",
          instrument,
          side: "BUY",
          quantity: "10",
          filled_quantity: "4",
          remaining_quantity: "6",
          price: "4000",
          status: "PARTIALLY_FILLED",
          observed_at: meta.fetched_at,
          reason: null,
        },
      ],
    },
    funds: {
      metadata: meta,
      values: {
        currency: "INR",
        available_cash: "125000",
        used_margin: "10000",
        collateral: null,
      },
    },
  };
  return {
    contract_version: "broker.read.v1",
    scenario_time: meta.fetched_at,
    providers: [{ provider_id: account.provider_id, name: "Provider Alpha" }],
    accounts: [room],
    position_aggregates: [
      {
        canonical_id: "NSE:HAL",
        exchange: "NSE",
        product: "INTRADAY",
        currency: "INR",
        quantity_unit: "SHARES",
        quantity: "100",
        qualified: true,
        contributions: [
          {
            broker_account_id: account.broker_account_id,
            quantity: "100",
            metadata: meta,
          },
        ],
      },
    ],
    unmapped_position_count: 1,
    missing_position_accounts: 0,
  };
}
