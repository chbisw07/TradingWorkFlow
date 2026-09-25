"use client";

import { useEffect, useState } from "react";
import {
  observationFreshness,
  observationTime,
  serviceFreshnessMs,
} from "../../lib/service-freshness";
import { StateBadge } from "../ui/surface-state";

type Status = {
  identity: { service_id: string; service_kind: string; provider: string };
  mode: "LOCAL" | "REMOTE" | "SYNTHETIC";
  enabled: boolean;
  active: boolean;
  health: "AVAILABLE" | "DEGRADED" | "UNAVAILABLE" | "UNKNOWN";
  observation: { synthetic: boolean; as_of: string } | null;
  error: string | null;
};

export function ServiceStatus() {
  const [services, setServices] = useState<Status[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(0);

  useEffect(() => {
    if (!services) return;
    const updateClock = () => setNow(Date.now());
    // One-shot expiry of the next fresh observation, never a network poll.
    const expiries = services.flatMap((service) => {
      const asOf = service.observation?.as_of;
      if (!asOf || observationFreshness(asOf, now) !== "fresh") return [];
      return [observationTime(asOf) + serviceFreshnessMs + 1];
    });
    const timer = expiries.length
      ? window.setTimeout(
          updateClock,
          Math.max(0, Math.min(...expiries) - Date.now()),
        )
      : undefined;
    document.addEventListener("visibilitychange", updateClock);
    window.addEventListener("focus", updateClock);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", updateClock);
      window.removeEventListener("focus", updateClock);
    };
  }, [services, now]);

  async function check() {
    setBusy(true);
    setError("");
    setServices(null);
    try {
      const response = await fetch("/api/v1/services", { cache: "no-store" });
      if (!response.ok) throw new Error("unavailable");
      const result = (await response.json()) as { services: Status[] };
      setNow(Date.now());
      setServices(result.services);
    } catch {
      setError("Service status unavailable. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="service-status" aria-busy={busy}>
      <p className="panel-intro">
        Optional service health snapshots. Fresh for five minutes after
        observation. No trading authority or live market data.
      </p>
      <button className="quiet-button" onClick={check} disabled={busy}>
        {busy ? "Checking services…" : "Check service status"}
      </button>
      <div role="status" aria-live="polite">
        {error && <p>{error}</p>}
        {!busy && !error && services === null && (
          <p className="panel-intro">
            Configured services have not been checked.
          </p>
        )}
        {services?.length === 0 && (
          <p className="panel-intro">No services configured.</p>
        )}
        {services && services.length > 0 && (
          <dl className="service-list">
            {services.map((service) => {
              const synthetic =
                service.mode === "SYNTHETIC" || service.observation?.synthetic;
              const asOf = service.observation?.as_of;
              const freshness = asOf ? observationFreshness(asOf, now) : null;
              const observedAt =
                asOf && Number.isFinite(observationTime(asOf))
                  ? new Date(observationTime(asOf)).toISOString()
                  : null;
              const label = !service.enabled
                ? "Disabled"
                : !service.active
                  ? "Inactive"
                  : service.health === "UNKNOWN"
                    ? "Unknown"
                    : service.health === "AVAILABLE"
                      ? "Available"
                      : service.health === "DEGRADED"
                        ? "Degraded"
                        : "Unavailable";
              const observedLabel = freshness
                ? `${label} · ${freshness}`
                : label;
              return (
                <div key={service.identity.service_id}>
                  <dt>
                    <span>
                      {service.identity.service_kind}
                      <small className="service-identity">
                        {service.identity.service_id}
                        {synthetic
                          ? " · Synthetic fixture"
                          : ` · ${service.mode}`}
                      </small>
                      <small className="service-identity">
                        Source: {service.identity.provider}
                      </small>
                      <small className="service-identity">
                        {observedAt ? (
                          <>
                            Observed{" "}
                            <time dateTime={observedAt}>
                              {observedAt
                                .replace("T", " ")
                                .replace(".000Z", " UTC")}
                            </time>
                          </>
                        ) : (
                          "No valid observation time"
                        )}
                      </small>
                    </span>
                  </dt>
                  <dd>
                    <StateBadge
                      state={
                        freshness === "stale"
                          ? "STALE"
                          : label === "Available" && freshness === "fresh"
                            ? "READY"
                            : label === "Degraded"
                              ? "STALE"
                              : "UNAVAILABLE"
                      }
                      label={observedLabel}
                    />
                  </dd>
                </div>
              );
            })}
          </dl>
        )}
      </div>
    </div>
  );
}
