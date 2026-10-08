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
export type FilterFieldType =
  | "NUMBER"
  | "PRICE"
  | "PERCENT"
  | "VOLUME"
  | "RATIO"
  | "BOOLEAN"
  | "ENUM"
  | "DIRECTION";
export type FilterField = {
  field: string;
  category: string;
  label: string;
  enabled: boolean;
  field_type: FilterFieldType;
  operators: string[];
  default_operator: string;
  default_value: number | string;
  comparison_fields: string[];
  enum_values: string[];
  minimum: number | null;
  maximum: number | null;
  minimum_exclusive: boolean;
  unit: string | null;
};
export type Catalog = {
  fields: FilterField[];
  templates: { name: string; filters: Filter[] }[];
  universes: Record<string, boolean>;
  universe_limitation: string;
};

export function fieldSpec(catalog: Catalog | null, field: string) {
  return catalog?.fields.find((item) => item.field === field);
}

export function filterCompatible(filter: Filter, catalog: Catalog | null) {
  const spec = fieldSpec(catalog, filter.field);
  if (!spec || !spec.operators.includes(filter.operator)) return false;
  const expectedSource = ["market_cap_inr", "pe_ratio"].includes(filter.field)
    ? "tapetide"
    : "internal";
  if (filter.source !== expectedSource) return false;
  if (Array.isArray(filter.value))
    return (
      filter.operator === "between" &&
      filter.value.length === 2 &&
      filter.value.every((item) => validLiteral(item, spec)) &&
      filter.value[0] <= filter.value[1]
    );
  if (filter.operator === "between") return false;
  if (typeof filter.value === "string")
    return spec.enum_values.length
      ? spec.enum_values.includes(filter.value)
      : spec.comparison_fields.includes(filter.value);
  return !spec.enum_values.length && validLiteral(filter.value, spec);
}

function validLiteral(value: number, spec: FilterField) {
  if (!Number.isFinite(value)) return false;
  if (
    spec.minimum !== null &&
    (spec.minimum_exclusive ? value <= spec.minimum : value < spec.minimum)
  )
    return false;
  return spec.maximum === null || value <= spec.maximum;
}

const OPERATOR_LABELS: Record<string, string> = {
  equals: "=",
  not_equals: "≠",
  between: "between",
  crosses_above: "crosses above",
  crosses_below: "crosses below",
};

export function filterExpression(filter: Filter, catalog: Catalog | null) {
  const spec = fieldSpec(catalog, filter.field);
  const left = spec?.label || filter.field;
  const operator = OPERATOR_LABELS[filter.operator] || filter.operator;
  let right: string;
  if (Array.isArray(filter.value)) right = filter.value.join(" and ");
  else if (typeof filter.value === "string")
    right = fieldSpec(catalog, filter.value)?.label || filter.value;
  else right = String(filter.value);
  return `${left} ${operator} ${right}`;
}
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
