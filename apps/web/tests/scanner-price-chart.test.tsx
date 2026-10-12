import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ScannerPriceChart } from "../src/components/scanner/scanner-price-chart";
import {
  scannerChartPoints,
  visibleScannerChartPoints,
  type ChartRange,
} from "../src/lib/scanner-chart";
import type { WatchBar } from "../src/lib/watchlists";

const bars: WatchBar[] = Array.from({ length: 260 }, (_, index) => {
  const close = 100 + index;
  return {
    timestamp: new Date(Date.UTC(2025, 0, index + 1)).toISOString(),
    open: close - 1,
    high: close + 2,
    low: close - 2,
    close,
    volume: index + 10,
  };
});

test("SMA20/50 use full archived lookback and ranges retain aligned OHLCV", () => {
  const points = scannerChartPoints(bars);
  expect(points[18].sma20).toBeNull();
  expect(points[48].sma50).toBeNull();
  expect(points[19].sma20).toBeCloseTo(109.5);
  expect(points[49].sma50).toBeCloseTo(124.5);
  expect(points.at(-1)?.sma20).toBeCloseTo(349.5);
  expect(points.at(-1)?.sma50).toBeCloseTo(334.5);
  const counts: Record<ChartRange, number> = {
    "1M": 22,
    "3M": 66,
    "6M": 132,
    "1Y": 252,
  };
  for (const [range, count] of Object.entries(counts) as [
    ChartRange,
    number,
  ][]) {
    const visible = visibleScannerChartPoints(points, range);
    expect(visible).toHaveLength(count);
    expect(visible[0].timestamp).toBe(bars[260 - count].timestamp);
    expect(visible[0].volume).toBe(bars[260 - count].volume);
    expect(visible.at(-1)?.sma50).toBeCloseTo(334.5);
  }
});

test("renders real candles, SMA overlays, volume and OHLC tooltip", () => {
  const { container } = render(
    <ScannerPriceChart bars={bars} range="3M" symbol="ALKEM" />,
  );
  expect(
    screen.getByRole("img", {
      name: /ALKEM 3M candlestick chart, 66 archived/,
    }),
  ).toBeInTheDocument();
  expect(container.querySelectorAll(".sc-candle-up rect")).toHaveLength(66);
  expect(container.querySelectorAll(".sc-volume-up")).toHaveLength(66);
  expect(
    container.querySelector(".sc-sma20-line")?.getAttribute("d"),
  ).toContain("L");
  expect(
    container.querySelector(".sc-sma50-line")?.getAttribute("d"),
  ).toContain("L");
  expect(container.querySelector(".sc-candle-up title")?.textContent).toContain(
    "Open",
  );
  expect(container.querySelector(".sc-candle-up title")?.textContent).toContain(
    "Volume",
  );
});

test("close-only archives use a line without inventing OHLC, and absent history stays local", () => {
  const closeOnly = bars.slice(0, 55).map((bar) => ({
    ...bar,
    open: undefined,
    high: undefined,
    low: undefined,
  })) as unknown as WatchBar[];
  const { container, rerender } = render(
    <ScannerPriceChart bars={closeOnly} range="3M" symbol="ALKEM" />,
  );
  expect(
    screen.getByRole("img", { name: /closing-price line/ }),
  ).toBeInTheDocument();
  expect(container.querySelector(".sc-close-line")).toBeInTheDocument();
  expect(
    container.querySelectorAll(".sc-candle-up, .sc-candle-down"),
  ).toHaveLength(0);
  expect(screen.getByText(/OHLC unavailable/)).toBeInTheDocument();
  rerender(<ScannerPriceChart bars={[]} range="3M" symbol="ALKEM" />);
  expect(screen.getByText(/Chart unavailable/)).toBeInTheDocument();
});
