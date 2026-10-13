import { describe, expect, test } from "vitest";
import { oiDisplay } from "../src/components/scanner/derivative-display";

describe("Derivative OI presentation", () => {
  test.each([
    ["Call long buildup", "call-long"],
    ["Put short buildup inferred", "put-short"],
    ["Put long buildup", "neutral"],
    ["Call short buildup", "neutral"],
    ["Short covering", "neutral"],
    ["Long unwinding", "neutral"],
    ["Mixed / Unclear", "neutral"],
    ["Insufficient evidence inferred", "neutral"],
    ["Inferred: Mixed / Unclear", "neutral"],
  ] as const)("keeps %s canonical and chooses %s tone", (canonical, tone) => {
    const snapshot = { label: canonical, inferred: true };
    expect(oiDisplay(snapshot.label)).toEqual({
      label: canonical
        .replace(/^inferred[:\s]+/i, "")
        .replace(/\s+inferred$/i, ""),
      tone,
    });
    expect(snapshot).toEqual({ label: canonical, inferred: true });
  });

  test("missing evidence stays neutral", () => {
    expect(oiDisplay(null)).toEqual({
      label: "Insufficient evidence",
      tone: "neutral",
    });
  });
});
