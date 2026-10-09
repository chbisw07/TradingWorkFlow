import type { SectorContextEvidence } from "../../lib/scanner";

const label = (value: string) => value.replaceAll("_", " ").toLowerCase();
const metric = (value: number | null, unit: string) =>
  value === null
    ? "Unavailable"
    : `${value > 0 ? "+" : ""}${value.toFixed(2)}${unit}`;
const time = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Unavailable";

export function SectorEvidence({
  evidence,
}: {
  evidence: SectorContextEvidence;
}) {
  const rows = [
    ["Sector", evidence.sector || "Unavailable"],
    ["Benchmark", evidence.context_benchmark || "Unmapped"],
    ["Benchmark trend", label(evidence.benchmark_trend)],
    ["Sector assessment", label(evidence.sector_state)],
    ["1D sector return", metric(evidence.benchmark_return_1d, "%")],
    ["5D sector return", metric(evidence.benchmark_return_5d, "%")],
    ["20D sector return", metric(evidence.benchmark_return_20d, "%")],
    ["5D vs NIFTY", metric(evidence.sector_rs_5d, " pp")],
    ["20D vs NIFTY", metric(evidence.sector_rs_20d, " pp")],
    [
      "5D candidate vs sector",
      metric(evidence.candidate_vs_sector_rs_5d, " pp"),
    ],
    [
      "20D candidate vs sector",
      metric(evidence.candidate_vs_sector_rs_20d, " pp"),
    ],
    ["Candidate relative strength", label(evidence.candidate_relative_state)],
    ["Rotation", label(evidence.rotation_state)],
    [
      "Contribution",
      `${evidence.contribution > 0 ? "+" : ""}${evidence.contribution}`,
    ],
  ];
  return (
    <section aria-label="Sector Context">
      <h3>Sector Context</h3>
      <p>Dhan · Completed daily bars · {label(evidence.status)}</p>
      <dl className="sc-metrics">
        {rows.map(([name, value]) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <small>
        Benchmark as of {time(evidence.as_of)}. Returns use completed sessions,
        not live quotes.
      </small>
      <details>
        <summary>Sector data details</summary>
        <p>Identity source: {evidence.identity_source}</p>
        <p>Metadata updated: {time(evidence.metadata_updated_at)}</p>
        <p>NIFTY as of: {time(evidence.nifty_as_of)}</p>
        <p>Candidate as of: {time(evidence.candidate_as_of)}</p>
        <p>Benchmark received: {time(evidence.received_at)}</p>
        <p>Freshness: {label(evidence.freshness)}</p>
        <p>
          NIFTY returns: 5D {metric(evidence.nifty_return_5d, "%")} · 20D{" "}
          {metric(evidence.nifty_return_20d, "%")}
        </p>
        <p>
          Candidate returns: 5D {metric(evidence.candidate_return_5d, "%")} ·
          20D {metric(evidence.candidate_return_20d, "%")}
        </p>
        <p>
          Candidate neutral band: ±{evidence.neutral_band_pp} pp · Policy{" "}
          {evidence.policy_version}
        </p>
      </details>
    </section>
  );
}
