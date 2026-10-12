import type { WatchBar } from "./watchlists";

export type ChartRange = "1M" | "3M" | "6M" | "1Y";
export const chartRanges: ChartRange[] = ["1M", "3M", "6M", "1Y"];
export const chartRangeBars: Record<ChartRange, number> = {
  "1M": 22,
  "3M": 66,
  "6M": 132,
  "1Y": 252,
};

export type ScannerChartPoint = {
  timestamp: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  volume: number | null;
  sma20: number | null;
  sma50: number | null;
};

const finite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

// Match the scanner's trailing-close SMA window. Compute over all archived
// completed bars before slicing the visible range, so lookback is preserved.
export function scannerChartPoints(bars: WatchBar[]): ScannerChartPoint[] {
  const points: ScannerChartPoint[] = [];
  for (const bar of bars) {
    if (
      !bar ||
      !finite(bar.close) ||
      !Number.isFinite(Date.parse(bar.timestamp))
    )
      continue;
    const ohlc =
      finite(bar.open) &&
      finite(bar.high) &&
      finite(bar.low) &&
      bar.low <= Math.min(bar.open, bar.close) &&
      bar.high >= Math.max(bar.open, bar.close);
    points.push({
      timestamp: bar.timestamp,
      open: ohlc ? bar.open : null,
      high: ohlc ? bar.high : null,
      low: ohlc ? bar.low : null,
      close: bar.close,
      volume: finite(bar.volume) && bar.volume >= 0 ? bar.volume : null,
      sma20: null,
      sma50: null,
    });
  }
  for (let i = 0; i < points.length; i++) {
    for (const period of [20, 50] as const) {
      if (i + 1 < period) continue;
      // Python's scanner uses fsum over the same trailing close window.
      const window = points.slice(i + 1 - period, i + 1);
      points[i][period === 20 ? "sma20" : "sma50"] =
        window.reduce((sum, point) => sum + point.close, 0) / period;
    }
  }
  return points;
}

export function visibleScannerChartPoints(
  points: ScannerChartPoint[],
  range: ChartRange,
): ScannerChartPoint[] {
  return points.slice(-chartRangeBars[range]);
}
