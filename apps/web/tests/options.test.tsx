import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { OptionsWorkspace } from "../src/components/options/options-workspace";
import { chainFixture } from "./fixtures/option-chain";
import { brokerApi } from "../src/lib/brokers";
import type { Capability } from "../src/lib/broker-orders";
vi.mock("next/navigation", () => ({ usePathname: () => "/options-analytics" }));
vi.mock("../src/lib/brokers", () => ({ brokerApi: vi.fn() }));
vi.mock("../src/components/brokers/order-ticket", () => ({
  OrderTicket: ({ canonical }: { canonical: unknown }) => (
    <div role="dialog">{JSON.stringify(canonical)}</div>
  ),
}));
let partial = false;
let unavailable = false;
let noSpot = false;
let fetcher: ReturnType<typeof vi.fn>;
const account = {
  id: "broker",
  provider: "zerodha",
  name: "Primary",
  state: "connected",
};
beforeEach(() => {
  partial = false;
  unavailable = false;
  noSpot = false;
  vi.mocked(brokerApi).mockImplementation(async (path) =>
    path === "accounts"
      ? [account]
      : ({
          enabled: true,
          broker: {
            supports_options: true,
            option_buy_supported: true,
            option_sell_supported: true,
          },
        } as Capability),
  );
  fetcher = vi.fn(async (path: string) => {
    const url = new URL(path, "http://localhost");
    if (unavailable)
      return Response.json(
        {
          error: { code: "provider_unavailable", message: "raw secret error" },
        },
        { status: 503 },
      );
    if (url.pathname.endsWith("underlyings"))
      return Response.json(
        ["NIFTY", "BANKNIFTY", "HDFCBANK"].filter((u) =>
          u.includes((url.searchParams.get("query") || "").toUpperCase()),
        ),
      );
    if (url.pathname.endsWith("expiries"))
      return Response.json(["2099-10-13", "2099-10-27"]);
    const data = chainFixture(
      url.searchParams.get("underlying") || "NIFTY",
      url.searchParams.get("expiry") || undefined,
      partial,
    );
    if (noSpot) {
      data.spot = null;
      data.atm_strike = null;
      data.warnings = ["spot_unavailable"];
      for (const r of data.rows) {
        r.is_atm = null;
        if (r.ce) r.ce.moneyness = null;
        if (r.pe) r.pe.moneyness = null;
      }
    }
    return Response.json(data);
  });
  vi.stubGlobal("fetch", fetcher);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
async function load() {
  render(<OptionsWorkspace />);
  fireEvent.focus(screen.getByRole("combobox", { name: "Underlying" }));
  fireEvent.click(await screen.findByRole("button", { name: "NIFTY" }));
  await screen.findByRole("table", { name: "Calls and puts option chain" });
}
const table = () =>
  within(screen.getByRole("table", { name: "Calls and puts option chain" }));

test("search uses canonical O2 underlyings, renders stock chain and nearest expiry", async () => {
  render(<OptionsWorkspace />);
  fireEvent.change(screen.getByLabelText("Underlying"), {
    target: { value: "HDFC" },
  });
  fireEvent.click(await screen.findByRole("button", { name: "HDFCBANK" }));
  await screen.findByRole("table", { name: "Calls and puts option chain" });
  expect(screen.getByLabelText("Expiry")).toHaveValue("2099-10-13");
  expect(
    screen.getByRole("heading", { name: "HDFCBANK option chain" }),
  ).toBeVisible();
  expect(screen.getByText("Provider source time unavailable")).toBeVisible();
});
test("chain preserves ATM, canonical moneyness, fields and exact CE Buy handoff", async () => {
  await load();
  expect(table().getAllByText("ATM").length).toBeGreaterThan(0);
  expect(table().getAllByText("ITM").length).toBeGreaterThan(0);
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 25000 CE" }),
  );
  expect(
    table().getByRole("button", { name: "Select NIFTY 25000 CE" }),
  ).toHaveAttribute("aria-pressed", "true");
  const detail = within(screen.getByLabelText("Selected contract"));
  expect(detail.getByText("Spread %")).toBeVisible();
  expect(detail.getByText("14.25")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Buy CE" }));
  expect(screen.getByRole("dialog")).toHaveTextContent(
    '"underlying_symbol":"NIFTY","expiry":"2099-10-13","strike":"25000","option_type":"CE"',
  );
  expect(screen.getByRole("dialog")).toHaveTextContent('"side":"BUY"');
});
test("PE selection preserves exact identity for Sell", async () => {
  await load();
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 25050 PE" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Sell PE" }));
  expect(screen.getByRole("dialog")).toHaveTextContent(
    '"strike":"25050","option_type":"PE"',
  );
  expect(screen.getByRole("dialog")).toHaveTextContent('"side":"SELL"');
});
test("expiry and window changes clear old scope; refresh preserves chosen expiry and leg", async () => {
  await load();
  fireEvent.change(screen.getByLabelText("Expiry"), {
    target: { value: "2099-10-27" },
  });
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(([p]) => p.includes("expiry=2099-10-27")),
    ).toBe(true),
  );
  await screen.findByRole("table", { name: "Calls and puts option chain" });
  fireEvent.change(screen.getByLabelText("Strike window"), {
    target: { value: "5" },
  });
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([p]) => p.includes("around_atm=5"))).toBe(
      true,
    ),
  );
  await screen.findByRole("table", { name: "Calls and puts option chain" });
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 25000 CE" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled(),
  );
  expect(screen.getByLabelText("Expiry")).toHaveValue("2099-10-27");
  expect(screen.getByLabelText("Strike window")).toHaveValue("5");
  expect(
    table().getByRole("button", { name: "Select NIFTY 25000 CE" }),
  ).toHaveAttribute("aria-pressed", "true");
});
test("partial quotes, missing PE, missing IV and Greeks preserve listed contracts", async () => {
  partial = true;
  await load();
  expect(
    table().queryByRole("button", { name: "Select NIFTY 24500 PE" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 24550 CE" }),
  );
  expect(screen.getByText(/Quote unavailable.*Broker preview/)).toBeVisible();
  expect(screen.getAllByText("—").length).toBeGreaterThan(4);
  expect(
    screen.getByText(
      "Partial chain. Available contracts and values are retained.",
    ),
  ).toBeVisible();
});
test("unavailable provider yields actionable message without raw error text", async () => {
  unavailable = true;
  render(<OptionsWorkspace />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Dhan market data unavailable",
  );
  expect(screen.queryByText(/raw secret/)).not.toBeInTheDocument();
});
test("no spot keeps rows and does not invent ATM", async () => {
  noSpot = true;
  await load();
  expect(table().queryByText("ATM")).not.toBeInTheDocument();
  expect(screen.getByText(/Underlying spot is unavailable/)).toBeVisible();
});
test("late response cannot replace a new underlying", async () => {
  let resolveOld: (r: Response) => void = () => {};
  const normal = fetcher.getMockImplementation() as (
    path: string,
  ) => Promise<Response>;
  fetcher.mockImplementation((path: string) =>
    path.includes("chain?") && path.includes("underlying=NIFTY&")
      ? new Promise<Response>((resolve) => {
          resolveOld = resolve;
        })
      : normal(path),
  );
  render(<OptionsWorkspace />);
  fireEvent.focus(screen.getByRole("combobox", { name: "Underlying" }));
  fireEvent.click(await screen.findByRole("button", { name: "NIFTY" }));
  await waitFor(() =>
    expect(fetcher.mock.calls.some(([p]) => p.includes("chain?"))).toBe(true),
  );
  fireEvent.focus(screen.getByRole("combobox", { name: "Underlying" }));
  fireEvent.click(await screen.findByRole("button", { name: "BANKNIFTY" }));
  await screen.findByRole("heading", { name: "BANKNIFTY option chain" });
  resolveOld(Response.json(chainFixture()));
  await waitFor(() =>
    expect(
      screen.queryByRole("heading", { name: "NIFTY option chain" }),
    ).not.toBeInTheDocument(),
  );
});
test("failed refresh preserves previous timestamp but prevents trade launch", async () => {
  await load();
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 25000 CE" }),
  );
  unavailable = true;
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await screen.findByRole("alert");
  expect(
    screen.getByText(/Showing the previously retrieved snapshot/),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Buy CE" })).toBeDisabled();
});

test("landing keeps suggestions interaction-only and presents a compact purposeful card", async () => {
  render(<OptionsWorkspace />);
  expect(
    screen.getByRole("heading", { name: "Explore an option chain" }),
  ).toBeVisible();
  expect(screen.getByText("Market data · Dhan")).toBeVisible();
  expect(
    screen.queryByLabelText("Underlying search results"),
  ).not.toBeInTheDocument();
  fireEvent.focus(screen.getByRole("combobox", { name: "Underlying" }));
  expect(await screen.findByRole("button", { name: "NIFTY" })).toBeVisible();
  fireEvent.keyDown(screen.getByRole("combobox", { name: "Underlying" }), {
    key: "Escape",
  });
  expect(
    screen.queryByLabelText("Underlying search results"),
  ).not.toBeInTheDocument();
  fireEvent.focus(screen.getByRole("combobox", { name: "Underlying" }));
  expect(screen.getByLabelText("Underlying search results")).toBeVisible();
  fireEvent.blur(screen.getByRole("combobox", { name: "Underlying" }), {
    relatedTarget: document.body,
  });
  expect(
    screen.queryByLabelText("Underlying search results"),
  ).not.toBeInTheDocument();
});

test("CE and PE halves follow independent canonical moneyness with an ATM landmark", async () => {
  await load();
  const ceItm = table()
    .getByRole("button", { name: "Select NIFTY 24500 CE" })
    .closest("td");
  const peOtm = table()
    .getByRole("button", { name: "Select NIFTY 24500 PE" })
    .closest("td");
  const ceAtm = table()
    .getByRole("button", { name: "Select NIFTY 25000 CE" })
    .closest("td");
  const peAtm = table()
    .getByRole("button", { name: "Select NIFTY 25000 PE" })
    .closest("td");
  const ceOtm = table()
    .getByRole("button", { name: "Select NIFTY 25500 CE" })
    .closest("td");
  const peItm = table()
    .getByRole("button", { name: "Select NIFTY 25500 PE" })
    .closest("td");
  expect(ceItm).toHaveClass("chain-money-itm");
  expect(peOtm).toHaveClass("chain-money-otm");
  expect(ceAtm).toHaveClass("chain-money-atm");
  expect(peAtm).toHaveClass("chain-money-atm");
  expect(ceOtm).toHaveClass("chain-money-otm");
  expect(peItm).toHaveClass("chain-money-itm");
  expect(ceAtm?.parentElement).toHaveClass("chain-atm");
  expect(
    within(ceAtm!.parentElement!.querySelector("th")!).getByText("ATM"),
  ).toBeVisible();
  expect(screen.getByLabelText("Moneyness legend")).toHaveTextContent("ITM");
  expect(screen.getByLabelText("Moneyness legend")).toHaveTextContent("OTM");
});

test("selected contract uses semantic badges, signed OI, source, and no raw identifier", async () => {
  await load();
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 24500 CE" }),
  );
  const detail = within(screen.getByLabelText("Selected contract"));
  expect(detail.getByText("CE", { selector: ".chain-badge" })).toBeVisible();
  expect(detail.getByText("ITM", { selector: ".chain-badge" })).toBeVisible();
  expect(detail.getByText("₹147.05")).toBeVisible();
  expect(detail.getByText("+30K")).toHaveClass("chain-value-positive");
  expect(detail.getByText("NFO · Dhan")).toBeVisible();
  expect(detail.queryByText(/NFO:NIFTY:/)).not.toBeInTheDocument();
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 25000 PE" }),
  );
  expect(detail.getByText("PE", { selector: ".chain-badge" })).toBeVisible();
  expect(detail.getByText("ATM", { selector: ".chain-badge" })).toBeVisible();
  fireEvent.click(detail.getByRole("button", { name: "Clear" }));
  expect(
    detail.getByRole("heading", { name: "Select a contract" }),
  ).toBeVisible();
  expect(
    detail.queryByRole("button", { name: "Buy PE" }),
  ).not.toBeInTheDocument();
});

test("negative and missing OI change retain typed visual states", async () => {
  const original = fetcher.getMockImplementation() as (
    path: string,
  ) => Promise<Response>;
  fetcher.mockImplementation(async (path: string) => {
    if (!path.includes("chain?")) return original(path);
    const response = await original(path);
    const data = await response.json();
    data.rows[0].pe.market.change_in_open_interest = "-160000";
    data.rows[1].ce.market.change_in_open_interest = null;
    return Response.json(data);
  });
  await load();
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 24500 PE" }),
  );
  expect(
    within(screen.getByLabelText("Selected contract")).getByText("−160K"),
  ).toHaveClass("chain-value-negative");
  fireEvent.click(
    table().getByRole("button", { name: "Select NIFTY 24550 CE" }),
  );
  expect(
    within(screen.getByLabelText("Selected contract")).getByText("—", {
      selector: "dd",
    }),
  ).toBeVisible();
});
