"use client";
import { useEffect, useState } from "react";
import { brokerApi, type Instrument } from "./brokers";

export type Quote = {
  reference: string;
  native_token: string;
  price: string | null;
  received_at: string;
};
type Batch = { received_at: string; quotes: Omit<Quote, "received_at">[] };
export const quoteKey = (i: Pick<Instrument, "reference" | "native_token">) =>
  `${i.reference}:${i.native_token}`;
export function freshQuote(
  q: Quote | undefined | null,
): q is Quote & { price: string } {
  if (
    !q ||
    !q.price ||
    !/^\d+(?:\.\d+)?$/.test(q.price) ||
    !(Number(q.price) > 0)
  )
    return false;
  const age = Date.now() - Date.parse(q.received_at);
  return Number.isFinite(age) && age >= -1000 && age < 5000;
}
// Exact decimal tick check: no floating-point rounding or silent price adjustment.
export function quotePrice(
  q: Quote | undefined | null,
  tick: string | null | undefined,
): string | null {
  if (!freshQuote(q) || !tick || !/^\d+(?:\.\d+)?$/.test(tick)) return null;
  const places = Math.max(
    q.price.split(".")[1]?.length || 0,
    tick.split(".")[1]?.length || 0,
  );
  if (places > 8) return null;
  const units = (v: string) => {
    const [whole, fraction = ""] = v.split(".");
    return BigInt(whole + fraction.padEnd(places, "0"));
  };
  const step = units(tick);
  return step > BigInt(0) && units(q.price) % step === BigInt(0)
    ? q.price
    : null;
}

export function useBrokerQuotes(base: string, instruments: Instrument[]) {
  const identities = JSON.stringify(
    instruments
      .slice(0, 30)
      .map(({ reference, native_token }) => ({ reference, native_token }))
      .sort((a, b) => quoteKey(a).localeCompare(quoteKey(b))),
  );
  const key = base + identities;
  const [state, setState] = useState<{
    key: string;
    quotes: Record<string, Quote>;
  }>({ key: "", quotes: {} });
  useEffect(() => {
    const items = JSON.parse(identities) as {
      reference: string;
      native_token: string;
    }[];
    if (!items.length) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let expiry: ReturnType<typeof setTimeout> | undefined;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController;
    async function poll() {
      const started = Date.now();
      controller = new AbortController();
      timeout = setTimeout(() => controller.abort(), 4000);
      try {
        const batch = await brokerApi<Batch>(
          base + "quotes",
          { instruments: items },
          controller.signal,
        );
        if (disposed || controller.signal.aborted) return;
        const quotes: Record<string, Quote> = {};
        for (const item of items) {
          const value = batch.quotes.find(
            (q) => quoteKey(q) === quoteKey(item),
          );
          const quote = value && { ...value, received_at: batch.received_at };
          if (freshQuote(quote)) quotes[quoteKey(item)] = quote;
        }
        clearTimeout(expiry);
        setState({ key, quotes });
        expiry = setTimeout(
          () => setState({ key, quotes: {} }),
          Math.max(0, Date.parse(batch.received_at) + 5000 - Date.now()),
        );
      } catch {
        if (!disposed) {
          clearTimeout(expiry);
          setState({ key, quotes: {} });
        }
      } finally {
        clearTimeout(timeout);
        if (!disposed)
          timer = setTimeout(
            () => void poll(),
            Math.max(0, 2000 - (Date.now() - started)),
          );
      }
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
      clearTimeout(expiry);
      clearTimeout(timeout);
      controller?.abort();
    };
  }, [base, identities, key]);
  return state.key === key ? state.quotes : {};
}
