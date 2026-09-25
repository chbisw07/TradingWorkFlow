import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ServiceStatus } from "../src/components/shell/service-status";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("status checks are explicit, and synthetic observations never claim live data", async () => {
  vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-25T12:00:00Z"));
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
          health: "AVAILABLE",
          observation: { synthetic: true, as_of: "2026-09-25T12:00:00Z" },
          error: null,
        },
        {
          identity: {
            service_id: "tm",
            service_kind: "TM",
            provider: "test-provider",
          },
          mode: "REMOTE",
          enabled: true,
          active: true,
          health: "DEGRADED",
          observation: { synthetic: false, as_of: "2026-09-25T12:00:00Z" },
          error: null,
        },
        {
          identity: {
            service_id: "llm",
            service_kind: "LLM",
            provider: "test-provider",
          },
          mode: "REMOTE",
          enabled: false,
          active: false,
          health: "UNKNOWN",
          observation: null,
          error: null,
        },
        {
          identity: {
            service_id: "scanner",
            service_kind: "SCANNER",
            provider: "test-provider",
          },
          mode: "LOCAL",
          enabled: true,
          active: false,
          health: "UNKNOWN",
          observation: null,
          error: null,
        },
      ],
    }),
  );
  vi.stubGlobal("fetch", fetcher);
  render(<ServiceStatus />);
  expect(fetcher).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Check service status" }));
  expect(await screen.findByText(/Synthetic fixture/)).toBeInTheDocument();
  for (const text of [
    "Available · fresh",
    "Degraded · fresh",
    "Disabled",
    "Inactive",
  ])
    expect(screen.getByText(text, { exact: true })).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/v1/services", {
    cache: "no-store",
  });
});

test("empty results and failed refresh clear old status and recover safely", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(Response.json({ services: [] }))
    .mockRejectedValueOnce(new Error("private-secret"))
    .mockResolvedValueOnce(Response.json({ services: [] }));
  vi.stubGlobal("fetch", fetcher);
  render(<ServiceStatus />);
  fireEvent.click(screen.getByRole("button", { name: "Check service status" }));
  expect(
    await screen.findByText("No services configured."),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Check service status" }));
  expect(
    await screen.findByText("Service status unavailable. Try again."),
  ).toBeInTheDocument();
  expect(screen.queryByText("No services configured.")).not.toBeInTheDocument();
  expect(screen.queryByText("private-secret")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Check service status" }));
  await waitFor(() =>
    expect(screen.queryByText(/Try again/)).not.toBeInTheDocument(),
  );
  expect(
    await screen.findByText("No services configured."),
  ).toBeInTheDocument();
});
