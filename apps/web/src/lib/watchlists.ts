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
export type WatchItem = {
  instrument: WatchInstrument;
  kind: Kind;
  ordering: number;
  added_at: string;
};
export type Watchlist = {
  id: string;
  name: string;
  description: string;
  favorite: boolean;
  archived: boolean;
  count: number;
  updated_at: string;
  revision: number;
};
export type WatchDetail = Watchlist & {
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
