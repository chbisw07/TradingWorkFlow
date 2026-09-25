/** TWF-1.6 display policy, independent of the service's reported health. */
export const serviceFreshnessMs = 5 * 60 * 1000;
export type Freshness = "fresh" | "stale" | "freshness unknown";

export function observationTime(asOf: string): number {
  // Never interpret a timestamp without a timezone in the viewer's local zone.
  return /(?:Z|[+-]\d{2}:\d{2})$/i.test(asOf) ? Date.parse(asOf) : NaN;
}

export function observationFreshness(asOf: string, now: number): Freshness {
  const age = now - observationTime(asOf);
  if (!Number.isFinite(age) || age < 0) return "freshness unknown";
  return age <= serviceFreshnessMs ? "fresh" : "stale";
}
