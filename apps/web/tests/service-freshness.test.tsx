import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ServiceStatus } from "../src/components/shell/service-status";
import {
  observationFreshness,
  serviceFreshnessMs,
} from "../src/lib/service-freshness";

const reference = Date.parse("2026-09-25T12:00:00Z");

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test.each([
  ["2026-09-25T12:00:00Z", "fresh"],
  ["2026-09-25T11:55:00Z", "fresh"],
  ["2026-09-25T11:54:59.999Z", "stale"],
  ["2026-09-25T17:30:00+05:30", "fresh"],
  ["2026-09-25T12:00:00.001Z", "freshness unknown"],
  ["invalid", "freshness unknown"],
  ["2026-09-25T12:00:00", "freshness unknown"],
])("freshness of %s is %s at the fixed reference time", (asOf, expected) => {
  expect(observationFreshness(asOf, reference)).toBe(expected);
});

function fixture(health: string, asOf: string | null) {
  const fetcher = vi.fn().mockResolvedValue(
    Response.json({
      services: [
        {
          identity: {
            service_id: "synthetic-ti",
            service_kind: "TI",
            provider: "twf-fixture",
          },
          mode: "SYNTHETIC",
          enabled: true,
          active: true,
          health,
          observation: asOf === null ? null : { synthetic: true, as_of: asOf },
          error: health === "UNAVAILABLE" ? "SERVICE_UNAVAILABLE" : null,
        },
      ],
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

test.each([
  ["AVAILABLE", "2026-09-25T12:00:00Z", "Available · fresh"],
  ["AVAILABLE", "2026-09-25T11:50:00Z", "Available · stale"],
  ["DEGRADED", "2026-09-25T12:00:00Z", "Degraded · fresh"],
  ["UNAVAILABLE", null, "Unavailable"],
  ["UNKNOWN", "2026-09-25T12:00:00Z", "Unknown · fresh"],
  ["AVAILABLE", "invalid", "Available · freshness unknown"],
])(
  "renders source, time and truthful %s observation",
  async (health, asOf, label) => {
    vi.spyOn(Date, "now").mockReturnValue(reference);
    fixture(health, asOf);
    render(<ServiceStatus />);
    fireEvent.click(
      screen.getByRole("button", { name: "Check service status" }),
    );
    expect(await screen.findByText(label, { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Source: twf-fixture")).toBeInTheDocument();
    expect(
      screen.queryByText("Available", { exact: true }),
    ).not.toBeInTheDocument();
    if (asOf && asOf !== "invalid") {
      const time = document.querySelector("time");
      expect(time).toHaveAttribute("datetime", new Date(asOf).toISOString());
      expect(time).toHaveTextContent("UTC");
    } else {
      expect(screen.getByText("No valid observation time")).toBeInTheDocument();
    }
  },
);

test("an open snapshot becomes stale after expiry without a network poll", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(reference);
  const fetcher = fixture("AVAILABLE", "2026-09-25T12:00:00Z");
  const view = render(<ServiceStatus />);
  await act(async () => {
    fireEvent.click(
      screen.getByRole("button", { name: "Check service status" }),
    );
  });
  expect(screen.getByText("Available · fresh")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(serviceFreshnessMs));
  expect(screen.getByText("Available · fresh")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(1));
  expect(screen.getByText("Available · stale")).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});
