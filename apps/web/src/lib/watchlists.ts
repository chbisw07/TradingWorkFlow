export type Kind = "EQUITY" | "INDEX" | "FUTURE" | "OPTION";
export type WatchInstrument = {
  instrument_id: string;
  symbol: string;
  exchange: string;
  segment: string;
  instrument_type: string;
  native: { namespace: string; native_id: string };
  expiry: string | null;
  strike: string | null;
  right: "CALL" | "PUT" | null;
};
export type InstrumentMetadataSummary = {
  applies_to_symbol: string;
  metadata_symbol: string;
  resolution_basis: "DIRECT" | "UNDERLYING";
  sector: string | null;
  industry: string | null;
  market_cap: number | null;
  market_cap_currency: string | null;
  market_cap_rank: number | null;
  market_cap_category: "LARGE" | "MID" | "SMALL" | null;
  twf_cap_tier: "LARGE" | "MID" | "SMALL" | "MICRO" | null;
  context_benchmark: string | null;
  context_benchmark_symbol: string | null;
  resolution_status: string;
  present_in_latest_snapshot: boolean;
  sector_as_of: string | null;
  industry_as_of: string | null;
  market_cap_as_of: string | null;
  dataset_generated_at: string;
  metadata_updated_at: string;
};
export type WatchItem = {
  instrument: WatchInstrument;
  kind: Kind;
  ordering: number;
  added_at: string;
  instrument_metadata?: InstrumentMetadataSummary | null;
};
export type Watchlist = {
  id: string;
  name: string;
  description: string;
  favorite: boolean;
  archived: boolean;
  count: number;
  updated_at: string | null;
  revision: number;
  ownership_kind: "USER" | "SYSTEM";
  read_only: boolean;
  system_code: string | null;
  enabled: boolean;
  availability: "READY" | "PARTIAL" | "DEFINITION_PENDING";
  pending_reason: string | null;
  expected_count: number | null;
  instrument_type_summary: Kind[];
  source_reference: string | null;
  source_received_at: string | null;
  freshness: "CURRENT" | "STALE" | "NOT_LOADED";
};
export type WatchDetail = Watchlist & {
  unresolved_count?: number;
  items: WatchItem[];
  notes: { id: string; text: string; created_at: string; author: string }[];
  activity: {
    id: string;
    action: string;
    symbol: string;
    created_at: string;
  }[];
};
export type WatchQuote = {
  instrument: WatchInstrument;
  last_price: string | null;
  previous_close: string | null;
  change_percent?: string | number | null;
  open: string | null;
  high: string | null;
  low: string | null;
  volume: string | null;
  provider: string;
  received_at: string;
  provider_source_time: string | null;
};
export type WatchBar = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};
export type WatchMetrics = {
  rsi14: number;
  trend: string;
  average_volume20: number | null;
  as_of: string;
  basis: string;
};
export type WatchChart = {
  metrics?: WatchMetrics | null;
  provider: string;
  bars: WatchBar[];
  interval?: string;
  received_at?: string;
  error: string | null;
};
export const badge: Record<Kind, string> = {
  EQUITY: "EQ",
  INDEX: "IDX",
  FUTURE: "FUT",
  OPTION: "OPT",
};
export const label: Record<Kind, string> = {
  EQUITY: "Equity",
  INDEX: "Indices",
  FUTURE: "Futures",
  OPTION: "Options",
};
export async function watchApi<T>(
  path = "",
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api/v1/watchlists" + path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal,
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      result?.error?.message || "Watchlist request failed. Please retry.",
    );
  return result;
}
export const numberText = (v: string | number | null | undefined) =>
  v == null
    ? "—"
    : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });
// Compare daily session dates in the exchange timezone, never today's open or
// the quote day's own close. Missing source time cannot establish a prior session.
export function previousClose(q?: WatchQuote, bars: WatchBar[] = []) {
  if (q?.previous_close != null && Number(q.previous_close) > 0)
    return Number(q.previous_close);
  if (!q?.provider_source_time) return null;
  const source = new Date(q.provider_source_time).getTime();
  if (!Number.isFinite(source)) return null;
  const session = (time: number) => Math.floor((time + 19800000) / 86400000);
  const prior = bars
    .filter((bar) => {
      const at = new Date(bar.timestamp).getTime();
      return (
        session(at) < session(source) &&
        source - at <= 7 * 86400000 &&
        Number.isFinite(Number(bar.close)) &&
        Number(bar.close) > 0
      );
    })
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))[0];
  return prior ? Number(prior.close) : null;
}
export function change(q?: WatchQuote, bars: WatchBar[] = []) {
  if (q?.change_percent != null && Number.isFinite(Number(q.change_percent)))
    return Number(q.change_percent);
  const previous = previousClose(q, bars);
  if (q?.last_price == null || previous == null) return null;
  const last = Number(q.last_price);
  if (!Number.isFinite(last) || last <= 0 || !Number.isFinite(previous))
    return null;
  return ((last - previous) / previous) * 100;
}

export function changeText(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "—";
  let digits = 2;
  while (digits < 6 && value !== 0 && Math.abs(value) < 0.5 * 10 ** -digits)
    digits += 1;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function periodChange(
  period: string,
  quote: WatchQuote | undefined,
  chart: WatchChart | null,
  daily: WatchBar[] = [],
) {
  // 1D is a quote/session comparison. Other windows compare the first and last
  // supplied completed daily closes (5/22/66/252 bars), not invented calendar dates.
  if (period === "1D")
    return {
      value: change(quote, daily),
      start: previousClose(quote, daily),
      end: quote?.last_price == null ? null : Number(quote.last_price),
      startTime: null,
      endTime: quote?.provider_source_time || null,
      basis: "Previous trading session close → latest quote",
    };
  const bars = chart?.interval === "1d" && !chart.error ? chart.bars : [];
  if (
    bars.length < 2 ||
    bars.some((b) => !Number.isFinite(Number(b.close)) || Number(b.close) <= 0)
  )
    return {
      value: null,
      start: null,
      end: null,
      startTime: null,
      endTime: null,
      basis: "Selected-period history unavailable",
    };
  const first = bars[0],
    last = bars.at(-1)!;
  return {
    value: (Number(last.close) / Number(first.close) - 1) * 100,
    start: Number(first.close),
    end: Number(last.close),
    startTime: first.timestamp,
    endTime: last.timestamp,
    basis: `${bars.length} completed daily bars · close to close`,
  };
}
export const sessionDate = (value: string) =>
  new Date(value).toLocaleDateString("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
export type WatchReference = {
  symbol: string;
  provider: string;
  tool: string;
  state: string;
  market_cap_inr: string | null;
  pe_ratio: string | null;
  high_52_week: string | null;
  low_52_week: string | null;
  received_at: string;
  source_time: string | null;
  freshness: string;
};

// Presentation only: all callers retain the original normalized numeric values.
export function indianVolume(value: string | number | null | undefined) {
  if (
    value == null ||
    value === "" ||
    !Number.isFinite(Number(value)) ||
    Number(value) < 0
  )
    return "—";
  const n = Number(value);
  const unit =
    n >= 1e7
      ? ([1e7, "Cr"] as const)
      : n >= 1e5
        ? ([1e5, "L"] as const)
        : n >= 1e3
          ? ([1e3, "K"] as const)
          : null;
  return unit
    ? `${(n / unit[0]).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${unit[1]}`
    : n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

// Input contract is market_cap_inr, already normalized to rupees by the API.
// One crore = 10^7 INR; one lakh crore = 10^12 INR. Never pass raw provider crores.
export function metadataMarketCap(
  metadata: InstrumentMetadataSummary | null | undefined,
) {
  if (!metadata?.market_cap) return "—";
  if (metadata.market_cap_currency === "INR")
    return indianMarketCap(metadata.market_cap);
  return `${numberText(metadata.market_cap)} ${metadata.market_cap_currency || ""}`.trim();
}

export function indianMarketCap(inr: string | number | null | undefined) {
  if (
    inr == null ||
    inr === "" ||
    !Number.isFinite(Number(inr)) ||
    Number(inr) <= 0
  )
    return "—";
  const n = Number(inr);
  if (n < 1e7) return `₹${numberText(n)}`;
  return `₹${(n / (n >= 1e12 ? 1e12 : 1e7)).toLocaleString("en-IN", { maximumFractionDigits: 2 })} ${n >= 1e12 ? "L Cr" : "Cr"}`;
}
