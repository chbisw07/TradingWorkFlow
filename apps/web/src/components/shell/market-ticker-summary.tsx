"use client";

import { useEffect, useState } from "react";

type MarketSummaryItem = {
  code: string;
  display_name: string;
  value: string | number | null;
  change_percent: string | number | null;
  source: string | null;
  source_time: string | null;
  freshness:
    | "CURRENT"
    | "DELAYED"
    | "LAST_SESSION"
    | "STALE"
    | "RECEIVED_TIME_ONLY"
    | "UNKNOWN";
  availability: "AVAILABLE" | "UNAVAILABLE";
};

type GlobalMarketSummary = {
  nifty: MarketSummaryItem;
  banknifty: MarketSummaryItem;
  india_vix: MarketSummaryItem;
  refresh_after_seconds: number;
};

const loading = ["NIFTY", "BANKNIFTY", "INDIA VIX"].map((name) => ({
  code: name,
  display_name: name,
  value: null,
  change_percent: null,
  source: null,
  source_time: null,
  freshness: "UNKNOWN" as const,
  availability: "UNAVAILABLE" as const,
}));

let pending: Promise<GlobalMarketSummary> | null = null;

function requestSummary(): Promise<GlobalMarketSummary> {
  if (!pending) {
    pending = fetch("/api/v1/market/summary", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    })
      .then((response) => {
        if (!response.ok) throw new Error("summary unavailable");
        return response.json() as Promise<GlobalMarketSummary>;
      })
      .finally(() => {
        pending = null;
      });
  }
  return pending;
}

function formatValue(item: MarketSummaryItem): string {
  if (item.availability !== "AVAILABLE" || item.value === null) return "—";
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(item.value));
}

function formatChange(item: MarketSummaryItem): string {
  if (item.availability !== "AVAILABLE" || item.change_percent === null)
    return "—";
  const value = Number(item.change_percent);
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function direction(
  item: MarketSummaryItem,
): "positive" | "negative" | "neutral" {
  const value = item.change_percent === null ? 0 : Number(item.change_percent);
  return value > 0 ? "positive" : value < 0 ? "negative" : "neutral";
}

function detail(item: MarketSummaryItem): string {
  if (item.availability !== "AVAILABLE")
    return `${item.display_name} unavailable`;
  const source = item.source ? `Source: ${item.source}.` : "";
  const timestamp = item.source_time
    ? ` Source time: ${new Date(item.source_time).toLocaleString("en-IN")}.`
    : " Source time unavailable; received-time freshness only.";
  return `${source}${timestamp} Freshness: ${item.freshness.toLowerCase().replaceAll("_", " ")}.`;
}

export function MarketTickerSummary() {
  const [items, setItems] = useState<MarketSummaryItem[]>(loading);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const result = await requestSummary();
        if (!active) return;
        setItems([result.nifty, result.banknifty, result.india_vix]);
        timer = setTimeout(load, result.refresh_after_seconds * 1000);
      } catch {
        if (active) timer = setTimeout(load, 60_000);
      }
    }
    void load();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, []);
  return (
    <dl className="market-ticker-summary" aria-label="Market summary">
      {items.map((item) => {
        const state = direction(item);
        const change = formatChange(item);
        const unavailable = item.availability !== "AVAILABLE";
        return (
          <div
            key={item.code}
            title={detail(item)}
            data-freshness={item.freshness}
          >
            <dt>{item.display_name}</dt>
            <dd>
              <strong
                aria-label={`${item.display_name} value ${formatValue(item)}`}
              >
                {formatValue(item)}
              </strong>
              <span
                className={`market-change ${state}`}
                aria-label={
                  unavailable
                    ? `${item.display_name} change unavailable`
                    : `${item.display_name} one day change ${change}`
                }
              >
                {change}
              </span>
              {item.freshness === "STALE" && (
                <small aria-label={`${item.display_name} data is stale`}>
                  Stale
                </small>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
