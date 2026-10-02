"use client";

import { useEffect, useMemo, useRef } from "react";
import type { EvidenceChart, EvidenceChartMode } from "../../lib/discovery";

const WIDTH = 760;
const PRICE_HEIGHT = 300;
const VOLUME_HEIGHT = 116;
const PAD = { left: 18, right: 66, top: 18, bottom: 28 };
const SERIES_COLORS = ["#40b9ff", "#f59e0b", "#a78bfa", "#2dd4bf"];

function number(value: string | number | null) {
  return value === null ? 0 : Number(value);
}

function metricValue(value: string | number, unit: string) {
  const parsed = number(value);
  if (unit === "boolean") return parsed ? "Yes" : "No";
  if (unit === "percent")
    return `${parsed >= 0 ? "+" : ""}${parsed.toFixed(2)}%`;
  if (unit === "ratio") return `${parsed.toFixed(2)}×`;
  if (unit === "index") return parsed.toFixed(1);
  if (unit === "volume")
    return parsed >= 1_000_000
      ? `${(parsed / 1_000_000).toFixed(2)}M`
      : parsed.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return parsed.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function operator(value: string) {
  return { LT: "<", LTE: "≤", EQ: "=", GTE: "≥", GT: ">" }[value] || value;
}

function dateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function pathFor(
  points: Array<{ timestamp: string; value: string | number }>,
  index: Map<string, number>,
  x: (position: number) => number,
  y: (value: number) => number,
) {
  return points
    .filter((point) => index.has(point.timestamp))
    .map(
      (point, position) =>
        `${position ? "L" : "M"}${x(index.get(point.timestamp)!)} ${y(number(point.value))}`,
    )
    .join(" ");
}

function PriceChart({ chart }: { chart: EvidenceChart }) {
  const bars = chart.bars;
  const priceSeries = chart.series.filter((item) => item.panel === "PRICE");
  const thresholds = chart.thresholds.filter((item) => item.panel === "PRICE");
  const values = [
    ...bars.flatMap((bar) => [number(bar.low), number(bar.high)]),
    ...priceSeries.flatMap((item) =>
      item.points.map((point) => number(point.value)),
    ),
    ...thresholds.map((item) => number(item.value)),
  ];
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const padding = Math.max((rawMax - rawMin) * 0.08, rawMax * 0.002, 0.01);
  const minimum = rawMin - padding;
  const maximum = rawMax + padding;
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = PRICE_HEIGHT - PAD.top - PAD.bottom;
  const x = (position: number) =>
    PAD.left + ((position + 0.5) / Math.max(bars.length, 1)) * plotWidth;
  const y = (value: number) =>
    PAD.top +
    ((maximum - value) / Math.max(maximum - minimum, 0.01)) * plotHeight;
  const step = plotWidth / Math.max(bars.length, 1);
  const candleWidth = Math.max(2, Math.min(7, step * 0.58));
  const indexes = new Map(bars.map((bar, index) => [bar.timestamp, index]));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(
    (fraction) => maximum - (maximum - minimum) * fraction,
  );
  const pullbackUpper = priceSeries.find(
    (item) => item.key === "pullback-upper",
  );
  const pullbackLower = new Map(
    priceSeries
      .find((item) => item.key === "pullback-lower")
      ?.points.map((point) => [point.timestamp, point.value]) || [],
  );
  const pullbackRegion = (pullbackUpper?.points || [])
    .filter(
      (point) =>
        indexes.has(point.timestamp) && pullbackLower.has(point.timestamp),
    )
    .map((point) => ({
      timestamp: point.timestamp,
      x: x(indexes.get(point.timestamp)!),
      upper: y(number(point.value)),
      lower: y(number(pullbackLower.get(point.timestamp)!)),
    }));
  const pullbackPath = pullbackRegion.length
    ? [
        `M${pullbackRegion[0].x} ${pullbackRegion[0].upper}`,
        ...pullbackRegion.slice(1).map((point) => `L${point.x} ${point.upper}`),
        ...[...pullbackRegion]
          .reverse()
          .map((point) => `L${point.x} ${point.lower}`),
        "Z",
      ].join(" ")
    : "";
  return (
    <figure className="evidence-chart-figure">
      <figcaption>
        <strong>Price evidence</strong>
        <span>{bars.length} completed daily bars · no post-scan data</span>
      </figcaption>
      <svg
        className="evidence-price-chart"
        viewBox={`0 0 ${WIDTH} ${PRICE_HEIGHT}`}
        role="img"
        aria-label={`${chart.instrument.symbol} candlestick chart through ${dateTime(chart.scan_time)}. Scan marker is on the final completed bar.`}
      >
        <title>{chart.instrument.symbol} price evidence</title>
        <desc>
          Candlesticks, scan-time marker, and only the price overlays used by
          the selected scan profile.
        </desc>
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              className="chart-gridline"
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
            />
            <text
              className="chart-axis-label"
              x={WIDTH - PAD.right + 8}
              y={y(tick) + 4}
            >
              {tick.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </text>
          </g>
        ))}
        {pullbackPath ? (
          <path
            className="chart-pullback-region"
            d={pullbackPath}
            aria-hidden="true"
          />
        ) : null}
        {thresholds.map((item) => (
          <g key={item.key}>
            <line
              className="chart-threshold"
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(number(item.value))}
              y2={y(number(item.value))}
            />
            <text
              className="chart-threshold-label"
              x={PAD.left + 6}
              y={y(number(item.value)) - 6}
            >
              {item.label}
            </text>
          </g>
        ))}
        {priceSeries.map((item, seriesIndex) => (
          <path
            key={item.key}
            className={`chart-indicator is-${item.key}`}
            d={pathFor(item.points, indexes, x, y)}
            style={{
              stroke: SERIES_COLORS[seriesIndex % SERIES_COLORS.length],
            }}
          />
        ))}
        {bars.map((bar, index) => {
          const open = y(number(bar.open));
          const close = y(number(bar.close));
          const up = number(bar.close) >= number(bar.open);
          return (
            <g
              key={bar.timestamp}
              className={up ? "candle is-up" : "candle is-down"}
            >
              <line
                x1={x(index)}
                x2={x(index)}
                y1={y(number(bar.high))}
                y2={y(number(bar.low))}
              />
              <rect
                x={x(index) - candleWidth / 2}
                y={Math.min(open, close)}
                width={candleWidth}
                height={Math.max(1.5, Math.abs(close - open))}
              />
            </g>
          );
        })}
        <line
          className="chart-scan-marker"
          x1={x(bars.length - 1)}
          x2={x(bars.length - 1)}
          y1={PAD.top}
          y2={PRICE_HEIGHT - PAD.bottom}
        />
        <text
          className="chart-marker-label"
          textAnchor="end"
          x={x(bars.length - 1) - 6}
          y={PAD.top + 13}
        >
          SCAN TIME
        </text>
        <text className="chart-axis-label" x={PAD.left} y={PRICE_HEIGHT - 7}>
          {new Date(bars[0].timestamp).toLocaleDateString()}
        </text>
        <text
          className="chart-axis-label"
          textAnchor="end"
          x={WIDTH - PAD.right}
          y={PRICE_HEIGHT - 7}
        >
          {new Date(bars.at(-1)!.timestamp).toLocaleDateString()}
        </text>
      </svg>
      <div className="evidence-chart-legend" aria-label="Price chart legend">
        <span>
          <i className="legend-candle" /> Price
        </span>
        {priceSeries.map((item, index) => (
          <span key={item.key}>
            <i
              style={{
                background: SERIES_COLORS[index % SERIES_COLORS.length],
              }}
            />
            {item.label}
          </span>
        ))}
        {thresholds.map((item) => (
          <span key={item.key}>
            <i className="legend-threshold" />
            {item.label}
          </span>
        ))}
      </div>
    </figure>
  );
}

function VolumeChart({ chart }: { chart: EvidenceChart }) {
  const bars = chart.bars;
  const baseline = chart.series.find((item) => item.panel === "VOLUME");
  const indexes = new Map(bars.map((bar, index) => [bar.timestamp, index]));
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const x = (position: number) =>
    PAD.left + ((position + 0.5) / Math.max(bars.length, 1)) * plotWidth;
  const maximum = Math.max(
    1,
    ...bars.map((bar) => number(bar.volume)),
    ...(baseline?.points.map((point) => number(point.value)) || []),
  );
  const y = (value: number) =>
    10 + (1 - value / maximum) * (VOLUME_HEIGHT - 34);
  const barWidth = Math.max(2, Math.min(8, (plotWidth / bars.length) * 0.62));
  return (
    <figure className="evidence-chart-figure is-volume">
      <figcaption>
        <strong>Volume evidence</strong>
        <span>Scan bar is highlighted</span>
      </figcaption>
      <svg
        className="evidence-volume-chart"
        viewBox={`0 0 ${WIDTH} ${VOLUME_HEIGHT}`}
        role="img"
        aria-label={`Volume chart for ${chart.instrument.symbol}; the final bar is the scan-time bar.`}
      >
        <title>{chart.instrument.symbol} volume evidence</title>
        {bars.map((bar, index) => (
          <rect
            key={bar.timestamp}
            className={`volume-bar${index === bars.length - 1 ? " is-scan" : ""}`}
            x={x(index) - barWidth / 2}
            y={y(number(bar.volume))}
            width={barWidth}
            height={VOLUME_HEIGHT - 24 - y(number(bar.volume))}
          />
        ))}
        {baseline ? (
          <path
            className="chart-volume-average"
            d={pathFor(baseline.points, indexes, x, y)}
          />
        ) : null}
        <line
          className="chart-scan-marker"
          x1={x(bars.length - 1)}
          x2={x(bars.length - 1)}
          y1={8}
          y2={VOLUME_HEIGHT - 24}
        />
      </svg>
      <div className="evidence-chart-legend">
        <span>
          <i className="legend-volume" /> Volume
        </span>
        {baseline ? (
          <span>
            <i className="legend-average" />
            {baseline.label}
          </span>
        ) : null}
      </div>
    </figure>
  );
}

function OscillatorChart({ chart }: { chart: EvidenceChart }) {
  const series = chart.series.filter((item) => item.panel === "OSCILLATOR");
  if (!series.length) return null;
  const thresholds = chart.thresholds.filter(
    (item) => item.panel === "OSCILLATOR",
  );
  const bars = chart.bars;
  const indexes = new Map(bars.map((bar, index) => [bar.timestamp, index]));
  const values = [
    ...series.flatMap((item) =>
      item.points.map((point) => number(point.value)),
    ),
    ...thresholds.map((item) => number(item.value)),
  ];
  const minimum = Math.min(...values, 0);
  const maximum = Math.max(...values, 1);
  const x = (position: number) =>
    PAD.left +
    ((position + 0.5) / bars.length) * (WIDTH - PAD.left - PAD.right);
  const y = (value: number) =>
    10 + ((maximum - value) / (maximum - minimum || 1)) * 72;
  return (
    <figure className="evidence-chart-figure is-oscillator">
      <figcaption>
        <strong>Profile signal</strong>
        <span>Only matched rule indicators</span>
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} 106`}
        role="img"
        aria-label="Momentum and oscillator evidence"
      >
        <title>Profile signal evidence</title>
        {thresholds.map((item) => (
          <line
            key={item.key}
            className="chart-threshold"
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={y(number(item.value))}
            y2={y(number(item.value))}
          />
        ))}
        {series.map((item, index) => (
          <path
            key={item.key}
            className="chart-indicator"
            d={pathFor(item.points, indexes, x, y)}
            style={{ stroke: SERIES_COLORS[index % SERIES_COLORS.length] }}
          />
        ))}
        <line
          className="chart-scan-marker"
          x1={x(bars.length - 1)}
          x2={x(bars.length - 1)}
          y1={8}
          y2={84}
        />
      </svg>
      <div className="evidence-chart-legend">
        {series.map((item, index) => (
          <span key={item.key}>
            <i
              style={{
                background: SERIES_COLORS[index % SERIES_COLORS.length],
              }}
            />
            {item.label}
          </span>
        ))}
      </div>
    </figure>
  );
}

export function EvidenceChartDrawer({
  chart,
  loading,
  onClose,
  onMode,
}: {
  chart: EvidenceChart | null;
  loading: boolean;
  onClose: () => void;
  onMode: (mode: EvidenceChartMode) => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const title = chart
    ? `${chart.instrument.symbol} evidence chart`
    : "Scan evidence chart";
  const accessibleSummary = useMemo(
    () =>
      chart?.predicates
        .map(
          (item) =>
            `${item.label}: ${metricValue(item.observed, item.unit)}, required ${operator(item.operator)} ${metricValue(item.threshold, item.unit)}, ${item.matched ? "passed" : "did not pass"}`,
        )
        .join(". ") || "",
    [chart],
  );
  useEffect(() => {
    const element = panel.current;
    if (!element) return;
    element.querySelector<HTMLElement>("button")?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !element) return;
      const focusable = [
        ...element.querySelectorAll<HTMLElement>("button:not([disabled])"),
      ];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [onClose]);

  return (
    <div
      className="evidence-drawer-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <aside
        ref={panel}
        className="evidence-chart-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-chart-title"
        aria-describedby="evidence-chart-summary"
      >
        <header className="evidence-drawer-header">
          <div>
            <p className="eyebrow">SCAN EVIDENCE CHART</p>
            <h2 id="evidence-chart-title">{title}</h2>
            <p>Visual verification of the exact normalized scan evidence.</p>
          </div>
          <button
            type="button"
            className="evidence-close"
            onClick={onClose}
            aria-label="Close evidence chart"
          >
            ×
          </button>
        </header>
        {chart ? (
          <div
            className="evidence-mode-tabs"
            role="tablist"
            aria-label="Chart data mode"
          >
            <button
              role="tab"
              aria-selected={chart.mode === "as_scanned"}
              onClick={() => onMode("as_scanned")}
            >
              As scanned
            </button>
            <button
              role="tab"
              aria-selected={chart.mode === "current"}
              onClick={() => onMode("current")}
            >
              Current chart
            </button>
          </div>
        ) : null}
        <div className="evidence-drawer-scroll">
          {loading ? (
            <div className="evidence-loading" role="status">
              Loading evidence chart…
            </div>
          ) : null}
          {!loading && chart ? (
            <>
              <section
                className="evidence-chart-context"
                aria-label="Chart context"
              >
                <div>
                  <span className={`evidence-mode-badge is-${chart.mode}`}>
                    {chart.mode === "as_scanned"
                      ? "AS SCANNED"
                      : "CURRENT CHART"}
                  </span>
                  <span className="evidence-data-badge">
                    {chart.data_mode === "SYNTHETIC"
                      ? "SYNTHETIC DATA"
                      : chart.data_mode}
                  </span>
                </div>
                <dl>
                  <div>
                    <dt>Profile</dt>
                    <dd>
                      {chart.profile.replaceAll("_", " ")} · v
                      {chart.profile_revision}
                    </dd>
                  </div>
                  <div>
                    <dt>Provider</dt>
                    <dd>{chart.provider}</dd>
                  </div>
                  <div>
                    <dt>
                      {chart.mode === "as_scanned"
                        ? "Scan time"
                        : "Last updated"}
                    </dt>
                    <dd>{dateTime(chart.scan_time)}</dd>
                  </div>
                  <div>
                    <dt>Basis</dt>
                    <dd>
                      {chart.timeframe} ·{" "}
                      {chart.bar_finality === "COMPLETED"
                        ? "Completed bars"
                        : "Finality unspecified"}
                    </dd>
                  </div>
                </dl>
              </section>
              {chart.state !== "AVAILABLE" ? (
                <section className="evidence-unavailable" role="status">
                  <strong>{chart.state.replaceAll("_", " ")}</strong>
                  <p>{chart.message}</p>
                  <p>Historical numerical predicates remain available below.</p>
                </section>
              ) : (
                <section
                  className="evidence-chart-surface"
                  aria-label="Visual evidence"
                >
                  <PriceChart chart={chart} />
                  <VolumeChart chart={chart} />
                  <OscillatorChart chart={chart} />
                </section>
              )}
              <section
                className="evidence-metric-section"
                aria-labelledby="key-metrics-title"
              >
                <div className="evidence-section-heading">
                  <p className="eyebrow">AT THE MARKER</p>
                  <h3 id="key-metrics-title">Key metrics</h3>
                </div>
                <div className="evidence-metric-grid">
                  {chart.metrics.map((item) => (
                    <article key={item.key}>
                      <span>{item.label}</span>
                      <strong>{metricValue(item.value, item.unit)}</strong>
                    </article>
                  ))}
                </div>
              </section>
              <section
                className="evidence-rules"
                aria-labelledby="why-matched-title"
              >
                <div className="evidence-section-heading">
                  <p className="eyebrow">NORMALIZED RULE EVIDENCE</p>
                  <h3 id="why-matched-title">Why this matched</h3>
                </div>
                <ul>
                  {chart.predicates.map((item) => (
                    <li
                      key={`${item.metric}-${item.operator}-${item.threshold}`}
                    >
                      <span
                        className={item.matched ? "rule-pass" : "rule-fail"}
                        aria-hidden="true"
                      >
                        {item.matched ? "✓" : "×"}
                      </span>
                      <div>
                        <strong>{item.label}</strong>
                        <span>
                          Observed {metricValue(item.observed, item.unit)} ·
                          Required {operator(item.operator)}{" "}
                          {metricValue(item.threshold, item.unit)}
                        </span>
                      </div>
                      <b>{item.matched ? "Passed" : "Not passed"}</b>
                    </li>
                  ))}
                </ul>
              </section>
              <section
                className="evidence-integrity-note"
                aria-label="Evidence provenance and retention"
              >
                <strong>Evidence integrity</strong>
                <p>
                  Run {chart.run_id.slice(0, 8)} · definition v
                  {chart.definition_revision} · {chart.provenance}
                </p>
                <p>{chart.retention.limitation}</p>
              </section>
              <p id="evidence-chart-summary" className="sr-only">
                {accessibleSummary}
              </p>
            </>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
