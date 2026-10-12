"use client";

import type { WatchBar } from "../../lib/watchlists";
import {
  scannerChartPoints,
  visibleScannerChartPoints,
  type ChartRange,
  type ScannerChartPoint,
} from "../../lib/scanner-chart";

const priceText = (value: number) =>
  new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: value < 100 ? 2 : 0,
  }).format(value);
const dateText = (timestamp: string) =>
  new Intl.DateTimeFormat("en-GB", {
    month: "short",
    year: "2-digit",
    timeZone: "Asia/Kolkata",
  })
    .format(new Date(timestamp))
    .replace(" ", " '");
const tooltipText = (point: ScannerChartPoint) =>
  [
    new Date(point.timestamp).toLocaleDateString("en-GB", {
      timeZone: "Asia/Kolkata",
    }),
    point.open === null ? null : `Open ${priceText(point.open)}`,
    point.high === null ? null : `High ${priceText(point.high)}`,
    point.low === null ? null : `Low ${priceText(point.low)}`,
    `Close ${priceText(point.close)}`,
    point.volume === null ? null : `Volume ${priceText(point.volume)}`,
    point.sma20 === null ? null : `SMA20 ${priceText(point.sma20)}`,
    point.sma50 === null ? null : `SMA50 ${priceText(point.sma50)}`,
  ]
    .filter(Boolean)
    .join(" · ");

export function ScannerPriceChart({
  bars,
  range,
  symbol,
}: {
  bars: WatchBar[];
  range: ChartRange;
  symbol: string;
}) {
  const all = scannerChartPoints(bars);
  const points = visibleScannerChartPoints(all, range);
  if (points.length < 2)
    return (
      <div className="sc-chart-unavailable" role="status">
        Chart unavailable · completed history missing
      </div>
    );

  const candles = points.every(
    (point) => point.open !== null && point.high !== null && point.low !== null,
  );
  const values = points
    .flatMap((point) => [
      point.low ?? point.close,
      point.high ?? point.close,
      point.sma20,
      point.sma50,
    ])
    .filter((value): value is number => value !== null);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const padding = Math.max(
    (maximum - minimum) * 0.06,
    Math.abs(maximum) * 0.001,
    0.01,
  );
  const low = minimum - padding;
  const high = maximum + padding;
  const plotLeft = 8;
  const plotRight = 359;
  const plotTop = 12;
  const plotBottom = 160;
  const volumeTop = 171;
  const volumeBottom = 198;
  const x = (index: number) =>
    plotLeft + ((index + 0.5) * (plotRight - plotLeft)) / points.length;
  const y = (value: number) =>
    plotBottom - ((value - low) / (high - low)) * (plotBottom - plotTop);
  const maxVolume = Math.max(...points.map((point) => point.volume ?? 0));
  const line = (key: "sma20" | "sma50") => {
    let started = false;
    return points
      .map((point, index) => {
        const value = point[key];
        if (value === null) {
          started = false;
          return "";
        }
        const command = started ? "L" : "M";
        started = true;
        return `${command}${x(index).toFixed(2)},${y(value).toFixed(2)}`;
      })
      .join(" ");
  };
  const closeLine = points
    .map(
      (point, index) =>
        `${index ? "L" : "M"}${x(index).toFixed(2)},${y(point.close).toFixed(2)}`,
    )
    .join(" ");
  const tickIndices = [
    ...new Set(
      [0, 1, 2, 3, 4].map((step) =>
        Math.min(
          points.length - 1,
          Math.round((step * (points.length - 1)) / 4),
        ),
      ),
    ),
  ];
  const candleWidth = Math.max(
    1,
    Math.min(5, ((plotRight - plotLeft) / points.length) * 0.62),
  );
  return (
    <div className="sc-candle-chart">
      <div className="sc-chart-legend" aria-hidden="true">
        <span className="sma20">
          SMA20{all.at(-1)?.sma20 === null ? " —" : ""}
        </span>
        <span className="sma50">
          SMA50{all.at(-1)?.sma50 === null ? " —" : ""}
        </span>
      </div>
      <svg
        viewBox="0 0 420 220"
        role="img"
        aria-label={`${symbol} ${range} ${candles ? "candlestick" : "closing-price line"} chart, ${points.length} archived completed daily bars, SMA20 and SMA50 where available, volume where available`}
      >
        {[0, 0.5, 1].map((fraction) => {
          const gy = plotTop + fraction * (plotBottom - plotTop);
          return (
            <g key={fraction}>
              <line
                x1={plotLeft}
                x2={plotRight}
                y1={gy}
                y2={gy}
                className="sc-chart-gridline"
              />
              <text x={365} y={gy + 3} className="sc-chart-axis">
                {priceText(high - fraction * (high - low))}
              </text>
            </g>
          );
        })}
        {candles ? (
          points.map((point, index) => {
            const up = point.close >= point.open!;
            const top = Math.min(y(point.open!), y(point.close));
            const height = Math.max(
              1,
              Math.abs(y(point.open!) - y(point.close)),
            );
            return (
              <g
                key={`${point.timestamp}-${index}`}
                className={up ? "sc-candle-up" : "sc-candle-down"}
              >
                <title>{tooltipText(point)}</title>
                <line
                  x1={x(index)}
                  x2={x(index)}
                  y1={y(point.high!)}
                  y2={y(point.low!)}
                />
                <rect
                  x={x(index) - candleWidth / 2}
                  y={top}
                  width={candleWidth}
                  height={height}
                />
              </g>
            );
          })
        ) : (
          <path d={closeLine} className="sc-close-line" />
        )}
        {(["sma20", "sma50"] as const).map((key) => (
          <path key={key} d={line(key)} className={`sc-${key}-line`} />
        ))}
        <line
          x1={plotLeft}
          x2={plotRight}
          y1={167}
          y2={167}
          className="sc-chart-gridline"
        />
        {maxVolume > 0 &&
          points.map((point, index) =>
            point.volume === null ? null : (
              <rect
                key={`volume-${point.timestamp}-${index}`}
                x={x(index) - candleWidth / 2}
                y={
                  volumeBottom -
                  (point.volume / maxVolume) * (volumeBottom - volumeTop)
                }
                width={candleWidth}
                height={(point.volume / maxVolume) * (volumeBottom - volumeTop)}
                className={
                  point.close >= (point.open ?? point.close)
                    ? "sc-volume-up"
                    : "sc-volume-down"
                }
              >
                <title>{tooltipText(point)}</title>
              </rect>
            ),
          )}
        {points.map((point, index) => (
          <rect
            key={`hover-${point.timestamp}-${index}`}
            x={plotLeft + (index * (plotRight - plotLeft)) / points.length}
            y={plotTop}
            width={(plotRight - plotLeft) / points.length}
            height={volumeBottom - plotTop}
            fill="transparent"
          >
            <title>{tooltipText(point)}</title>
          </rect>
        ))}
        {tickIndices.map((index) => (
          <text
            key={`date-${index}`}
            x={x(index)}
            y={214}
            textAnchor={
              index === 0
                ? "start"
                : index === points.length - 1
                  ? "end"
                  : "middle"
            }
            className="sc-chart-axis"
          >
            {dateText(points[index].timestamp)}
          </text>
        ))}
      </svg>
      {!candles && (
        <small className="sc-chart-note">
          OHLC unavailable · closing-price line
        </small>
      )}
    </div>
  );
}
