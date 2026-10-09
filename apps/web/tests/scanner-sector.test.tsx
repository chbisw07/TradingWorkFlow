import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { SectorEvidence } from "../src/components/scanner/sector-evidence";
import type { SectorContextEvidence } from "../src/lib/scanner";

const evidence: SectorContextEvidence = {
  policy_version: "sector.v1",
  sector: "Technology",
  industry: "IT Services",
  context_benchmark: "NIFTY IT",
  context_benchmark_symbol: "NIFTYIT",
  benchmark_trend: "BULLISH",
  benchmark_return_1d: 1,
  benchmark_return_5d: 3.1,
  benchmark_return_20d: 7.8,
  nifty_return_5d: 0.7,
  nifty_return_20d: 3.7,
  sector_rs_5d: 2.4,
  sector_rs_20d: 4.1,
  candidate_return_5d: 4.7,
  candidate_return_20d: 8.9,
  candidate_vs_sector_rs_5d: 1.6,
  candidate_vs_sector_rs_20d: 1.1,
  candidate_relative_state: "OUTPERFORMING",
  rotation_state: "IMPROVING",
  sector_state: "STRONG",
  contribution: 5,
  status: "AVAILABLE",
  source: "dhan",
  identity_source: "Instrument Metadata",
  as_of: "2026-10-08T10:00:00Z",
  nifty_as_of: "2026-10-08T10:00:00Z",
  candidate_as_of: "2026-10-08T10:00:00Z",
  received_at: "2026-10-09T10:00:00Z",
  metadata_updated_at: "2026-10-09T09:00:00Z",
  freshness: "COMPLETED_DAILY_AS_OF",
  missing_evidence: [],
  warnings: [],
  neutral_band_pp: 0.25,
};

test("sector evidence renders persisted metrics with units, source and accessible details", () => {
  render(<SectorEvidence evidence={evidence} />);
  const panel = screen.getByRole("region", { name: "Sector Context" });
  expect(panel).toHaveTextContent("Technology");
  expect(panel).toHaveTextContent("NIFTY IT");
  expect(panel).toHaveTextContent("+3.10%");
  expect(panel).toHaveTextContent("+2.40 pp");
  expect(panel).toHaveTextContent("+1.60 pp");
  expect(panel).toHaveTextContent("outperforming");
  expect(panel).toHaveTextContent("Dhan · Completed daily bars");
  const summary = within(panel).getByText("Sector data details");
  fireEvent.click(summary);
  expect(summary.parentElement).toHaveAttribute("open");
  expect(panel).toHaveTextContent("Identity source: Instrument Metadata");
  expect(panel).not.toHaveTextContent("security_id");
});

test("missing and direction-neutral evidence stays explicit instead of inventing zero returns", () => {
  render(
    <SectorEvidence
      evidence={{
        ...evidence,
        context_benchmark: null,
        benchmark_return_5d: null,
        sector_rs_5d: null,
        sector_state: "UNKNOWN",
        contribution: 0,
        status: "UNAVAILABLE",
      }}
    />,
  );
  const panel = screen.getByRole("region", { name: "Sector Context" });
  expect(panel).toHaveTextContent("Unmapped");
  expect(panel).toHaveTextContent("unknown");
  expect(panel).toHaveTextContent("5D sector returnUnavailable");
  expect(panel).toHaveTextContent("Contribution0");
});
