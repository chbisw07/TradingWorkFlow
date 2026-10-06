"use client";
import type { WatchBar } from "../../lib/watchlists";
// Provider-independent renderer: only normalized OHLCV enters this component.
export function MarketChart({
  bars,
  compact = false,
}: {
  bars: WatchBar[];
  compact?: boolean;
}) {
  if (bars.length < 2)
    return compact ? (
      <span
        className="wl-unavailable"
        title="Quick chart unavailable"
        aria-label="Quick chart unavailable"
      >
        —
      </span>
    ) : (
      <span className="wl-unavailable">Chart unavailable</span>
    );
  const w = compact ? 120 : 300,
    h = compact ? 30 : 190,
    p = compact ? 2 : 24;
  const lo = Math.min(...bars.map((b) => b.low)),
    hi = Math.max(...bars.map((b) => b.high));
  const x = (i: number) => p + (i * (w - 2 * p)) / (bars.length - 1);
  const y = (n: number) => h - p - ((n - lo) * (h - 2 * p)) / (hi - lo || 1);
  const path = bars
    .map((b, i) => `${i ? "L" : "M"}${x(i)},${y(b.close)}`)
    .join(" ");
  const up = bars.at(-1)!.close >= bars[0].close;
  return (
    <svg
      className={`wl-chart ${up ? "up" : "down"}`}
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label={`${compact ? "Quick" : "Price"} chart, ${bars.length} completed bars`}
    >
      {!compact &&
        [0, 0.5, 1].map((f) => (
          <g key={f}>
            <line
              x1={p}
              x2={w - p}
              y1={p + (h - 2 * p) * f}
              y2={p + (h - 2 * p) * f}
              stroke="var(--shell-border)"
            />
            <text
              x={p}
              y={p + (h - 2 * p) * f - 4}
              fill="currentColor"
              fontSize="11"
            >
              {(hi - (hi - lo) * f).toFixed(2)}
            </text>
          </g>
        ))}
      {!compact && (
        <path
          d={`${path} L${x(bars.length - 1)},${h - p} L${p},${h - p} Z`}
          fill="currentColor"
          opacity=".08"
        />
      )}
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth={compact ? 1.5 : 2}
      />
      {!compact && (
        <>
          <text x={p} y={h - 4} fill="var(--shell-secondary)" fontSize="11">
            {bars[0].timestamp.slice(0, 10)}
          </text>
          <text
            x={w - p}
            y={h - 4}
            textAnchor="end"
            fill="var(--shell-secondary)"
            fontSize="11"
          >
            {bars.at(-1)!.timestamp.slice(0, 10)}
          </text>
        </>
      )}
    </svg>
  );
}
