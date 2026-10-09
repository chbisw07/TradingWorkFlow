import type {
  OptionChainSnapshot,
  OptionLegSnapshot,
} from "../../src/lib/options";
export function chainFixture(
  underlying = "NIFTY",
  expiry = "2099-10-13",
  partial = false,
): OptionChainSnapshot {
  function leg(strike: number, side: "CE" | "PE"): OptionLegSnapshot {
    return {
      contract: {
        canonical_id: `NFO:${underlying}:${expiry}:${strike}:${side}`,
        exchange: "NFO",
        segment: "NFO-OPT",
        underlying_symbol: underlying,
        underlying_type: underlying === "HDFCBANK" ? "EQUITY" : "INDEX",
        expiry,
        strike: String(strike),
        option_type: side,
        lot_size: 65,
        display_symbol: `${underlying} ${expiry} ${strike} ${side}`,
        tick_size: "0.05",
        freeze_quantity: null,
        contract_multiplier: null,
        currency: "INR",
        is_active: true,
        last_trading_date: expiry,
      },
      moneyness:
        strike === 25000
          ? "ATM"
          : strike < 25000 === (side === "CE")
            ? "ITM"
            : "OTM",
      market: {
        ltp: "147.05",
        bid: "146.90",
        ask: "147.15",
        bid_quantity: "650",
        ask_quantity: "130",
        spread: "0.25",
        spread_percent: "0.17",
        volume: "230400",
        open_interest: "850000",
        previous_open_interest: "820000",
        change_in_open_interest: "30000",
        implied_volatility: partial ? null : "14.25",
        delta: partial ? null : "0.52",
        gamma: partial ? null : "0.00017",
        theta: partial ? null : "-5.1",
        vega: partial ? null : "8.9",
        source_time: null,
      },
      availability: "AVAILABLE",
      warnings: [],
    };
  }
  const rows = Array.from({ length: 21 }, (_, i) => {
    const strike = 24500 + i * 50;
    return {
      strike: String(strike),
      is_atm: strike === 25000,
      distance_from_spot: String(strike - 25000),
      distance_percent: String((strike - 25000) / 250),
      ce: leg(strike, "CE"),
      pe: partial && i === 0 ? null : leg(strike, "PE"),
    };
  });
  if (partial) {
    rows[1].ce.market.ltp = null;
    rows[1].ce.availability = "UNAVAILABLE";
  }
  return {
    underlying,
    expiry,
    spot: "25000",
    atm_strike: "25000",
    dte: Math.max(
      0,
      Math.round(
        (Date.parse(`${expiry}T00:00:00Z`) -
          Date.parse("2026-10-10T00:00:00Z")) /
          86400000,
      ),
    ),
    as_of: "2026-10-10T06:12:05Z",
    rows,
    status: partial ? "PARTIAL" : "COMPLETE",
    capabilities: {
      provider: "dhan",
      contracts: "SUPPORTED",
      quotes: "SUPPORTED",
      bid_ask: "SUPPORTED",
      volume: "SUPPORTED",
      open_interest: "SUPPORTED",
      oi_change: "SUPPORTED",
      iv: "PARTIAL",
      greeks: "PARTIAL",
    },
    provenance: {
      provider: "dhan",
      contract_source: "instrument-master",
      market_source: "option-chain",
      master_received_at: "2026-10-10T03:00:00Z",
      received_at: "2026-10-10T06:12:05Z",
      source_time: null,
      freshness: "SOURCE_TIME_UNAVAILABLE",
      quote_ttl_seconds: 5,
      cached: false,
      oi_unit: "contracts",
      iv_unit: "percent",
    },
    warnings: partial ? ["partial_chain", "quote_unavailable"] : [],
    missing_capabilities: [],
  };
}
