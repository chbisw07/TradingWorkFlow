import { expect, test } from "vitest";
import { conciseMatchReason } from "../src/lib/scanner-presentation";
import type { ScanRow } from "../src/lib/scanner";

const diagnostic = {
  filter: {
    field: "trend",
    operator: "equals",
    value: "Down",
    timeframe: "1d" as const,
    version: "1" as const,
    source: "internal" as const,
  },
  observed: "Down",
  threshold: "Down",
  passed: true,
  reason: "Trend versus SMA20 is down",
};

test("table reason comes from a passed predicate, while ranking stays separate", () => {
  const row = {
    symbol: "ADANIGREEN",
    outcome: "MATCH",
    diagnostics: [diagnostic],
    analysis: {
      context_classification: "SUPPORTIVE",
      context_adjustment: 6,
      final_relevance: 86,
      short_reason: "1/1 technical · Context +6 Supportive · Final 86",
    },
  } as ScanRow;
  expect(conciseMatchReason(row, null)).toBe("Trend Down · Supportive");
  expect(
    conciseMatchReason(
      { ...row, diagnostics: [{ ...diagnostic, passed: false }] },
      null,
    ),
  ).toBe("Matched filters");
  expect(
    conciseMatchReason(
      { ...row, analysis: { ...row.analysis!, context_adjustment: 0 } },
      null,
    ),
  ).toBe("Trend Down");
});
