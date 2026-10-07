import type { WatchInstrument, WatchBar } from "./watchlists";
export type Filter = {
  field: string;
  operator: string;
  value: number | string | [number, number];
  timeframe: "1d";
  version: "1";
  source: "internal" | "tapetide";
};
export type Config = {
  name: string;
  scanner_type: "EQUITY_INDEX";
  data_mode: "REAL";
  provider: "dhan";
  universe: {
    source: string;
    watchlist_id?: string;
    symbols: string[];
    instrument_ids: string[];
  };
  filters: Filter[];
  sort: string;
  version: "1";
};
export type ScanRow = {
  symbol: string;
  instrument?: WatchInstrument;
  outcome: "MATCH" | "NON_MATCH" | "NOT_EVALUATED";
  failure?: string;
  metrics?: Record<string, number | string | null>;
  bars?: WatchBar[];
  quote?: {
    last_price: string;
    provider: string;
    received_at: string;
    provider_source_time: string | null;
  };
  source_time?: string;
  received_at?: string;
  basis?: string;
  diagnostics?: {
    filter: Filter;
    observed: number | string | null;
    threshold: unknown;
    passed: boolean | null;
    reason: string;
  }[];
};
export type Run = {
  id: string;
  created_at: string;
  config: Config;
  data_mode: string;
  market_data_provider: string;
  counts: Record<string, number>;
  rows: ScanRow[];
};
export type Saved = {
  id: string;
  config: Config;
  archived: boolean;
  updated_at: string;
};
export type Catalog = {
  fields: {
    field: string;
    category: string;
    label: string;
    enabled: boolean;
  }[];
  templates: { name: string; filters: Filter[] }[];
  universes: Record<string, boolean>;
  universe_limitation: string;
};
export type ProviderResults = {
  state: string;
  tool?: string;
  coverage?: string;
  received_at?: string;
  freshness?: string;
  rows: {
    symbol: string;
    provider: string;
    tool: string;
    bucket: string;
    buckets?: string[];
    metrics: Record<string, number | null>;
    reasons: string[];
  }[];
};
export async function scannerApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/v1/scanner/" + path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      value.error?.message || "Scanner request could not be completed.",
    );
  return value as T;
}
export const initialConfig: Config = {
  name: "RSI Oversold",
  scanner_type: "EQUITY_INDEX",
  data_mode: "REAL",
  provider: "dhan",
  universe: { source: "CUSTOM", symbols: [], instrument_ids: [] },
  filters: [
    {
      field: "rsi",
      operator: "<",
      value: 30,
      timeframe: "1d",
      version: "1",
      source: "internal",
    },
  ],
  sort: "symbol",
  version: "1",
};
