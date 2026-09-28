import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { OrderTicket } from "../src/components/brokers/order-ticket";
import type { Account, Instrument } from "../src/lib/brokers";
import type { Choices } from "../src/lib/broker-orders";
const account: Account = {
  id: "account",
  provider: "zerodha",
  name: "Primary",
  identity: "AB1234",
  state: "connected",
  health: "healthy",
  generation: 1,
  updated_at: "",
  last_read_at: null,
};
const equity: Instrument = {
  symbol: "RELIANCE",
  name: "RELIANCE INDUSTRIES",
  exchange: "NSE",
  segment: "NSE",
  kind: "EQ",
  reference: "ZERODHA:NSE:RELIANCE",
  native_token: "11",
  lot_size: "1",
  tick_size: "0.05",
};
const bse = {
  ...equity,
  exchange: "BSE",
  segment: "BSE",
  reference: "ZERODHA:BSE:RELIANCE",
  native_token: "12",
};
const empty: Choices = {
  underlyings: [],
  expiries: [],
  option_types: [],
  strikes: [],
  instruments: [],
  total: 0,
  page: 1,
};
const params = (url: unknown) =>
  new URL(String(url), "http://localhost").searchParams;
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});
afterEach(() => vi.restoreAllMocks());
function open() {
  render(<OrderTicket account={account} close={() => {}} />);
}

test("NSE default, explicit exchange requests, page reset and BSE execution identity", async () => {
  const fetch = vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    if (String(url).includes("capabilities"))
      return Response.json({
        enabled: true,
        instrument: bse,
        products: ["CNC"],
        quantity_unit: "shares",
        max_quantity: 1000000,
        order_types: [
          {
            name: "LIMIT",
            price_required: true,
            trigger_required: false,
            validities: ["DAY"],
          },
        ],
      });
    const q = params(url);
    return Response.json({
      ...empty,
      page: Number(q.get("page")),
      total: 61,
      instruments:
        q.get("exchange") === "BOTH"
          ? [equity, bse]
          : q.get("exchange") === "BSE"
            ? [bse]
            : [equity],
    });
  });
  open();
  expect(screen.getByRole("radio", { name: "Equity" })).toBeChecked();
  expect(screen.getByRole("radio", { name: "NSE" })).toBeChecked();
  fireEvent.change(screen.getByLabelText("Search stock"), {
    target: { value: "reliance" },
  });
  await screen.findByRole("button", { name: "Buy RELIANCE" });
  expect(params(fetch.mock.calls.at(-1)![0]).get("exchange")).toBe("NSE");
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() =>
    expect(params(fetch.mock.calls.at(-1)![0]).get("page")).toBe("2"),
  );
  fireEvent.click(screen.getByRole("radio", { name: "Both" }));
  await waitFor(() =>
    expect(
      screen.getAllByRole("button", { name: "Buy RELIANCE" }),
    ).toHaveLength(2),
  );
  expect(params(fetch.mock.calls.at(-1)![0]).get("page")).toBe("1");
  expect(screen.getByText("NSE · Equity")).toBeVisible();
  expect(screen.getByText("BSE · Equity")).toBeVisible();
  fireEvent.click(screen.getByRole("radio", { name: "BSE" }));
  await screen.findByRole("button", { name: "Buy RELIANCE" });
  expect(screen.queryByText("NSE · Equity")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Buy RELIANCE" }));
  await screen.findByLabelText("Quantity");
  const identity = params(
    fetch.mock.calls.find((call) =>
      String(call[0]).includes("capabilities"),
    )![0],
  );
  expect(identity.get("reference")).toBe(bse.reference);
  expect(identity.get("native_token")).toBe(bse.native_token);
});

test("late search results and errors cannot replace a newer filter selection", async () => {
  const requests: {
    url: string;
    resolve: (r: Response) => void;
    reject: (e: Error) => void;
  }[] = [];
  vi.spyOn(global, "fetch").mockImplementation(
    (url) =>
      new Promise((resolve, reject) => {
        requests.push({ url: String(url), resolve, reject });
      }),
  );
  open();
  fireEvent.change(screen.getByLabelText("Search stock"), {
    target: { value: "older" },
  });
  await waitFor(() => expect(requests).toHaveLength(1));
  fireEvent.change(screen.getByLabelText("Search stock"), {
    target: { value: "reliance" },
  });
  await waitFor(() => expect(requests).toHaveLength(2));
  await act(async () =>
    requests[1].resolve(
      Response.json({ ...empty, instruments: [equity], total: 1 }),
    ),
  );
  await screen.findByRole("button", { name: "Buy RELIANCE" });
  await act(async () =>
    requests[0].resolve(
      Response.json({
        ...empty,
        instruments: [{ ...equity, symbol: "OLD" }],
        total: 1,
      }),
    ),
  );
  expect(screen.queryByRole("button", { name: "Buy OLD" })).toBeNull();
  expect(screen.getByRole("button", { name: "Buy RELIANCE" })).toBeVisible();
  fireEvent.click(screen.getByRole("radio", { name: "BSE" }));
  expect(screen.queryByRole("button", { name: "Buy RELIANCE" })).toBeNull();
  await waitFor(() => expect(requests).toHaveLength(3));
  fireEvent.click(screen.getByRole("radio", { name: "Both" }));
  await waitFor(() => expect(requests).toHaveLength(4));
  await act(async () => requests[2].reject(new Error("obsolete failure")));
  expect(screen.queryByRole("alert")).toBeNull();
  await act(async () => requests[3].resolve(Response.json(empty)));
  await screen.findByText("No matching executable instruments.");
});

test("derivative filters are dependent, reset downstream selections and omit equity exchange", async () => {
  const fetch = vi
    .spyOn(global, "fetch")
    .mockResolvedValue(Response.json(empty));
  // New Response each time because brokerApi consumes the response body.
  fetch.mockImplementation(async () =>
    Response.json({
      ...empty,
      underlyings: ["RELIANCE"],
      expiries: ["2099-10-29", "2099-11-26"],
      option_types: ["CE", "PE"],
      strikes: ["1400", "1500"],
    }),
  );
  open();
  fireEvent.click(screen.getByRole("radio", { name: "Options" }));
  expect(screen.queryByRole("group", { name: "Exchange" })).toBeNull();
  expect(screen.getByLabelText("Expiry")).toBeDisabled();
  expect(screen.getByLabelText("Option type")).toBeDisabled();
  expect(screen.getByLabelText("Strike")).toBeDisabled();
  await screen.findByRole("option", { name: "RELIANCE" });
  fireEvent.change(screen.getByRole("combobox", { name: "Underlying" }), {
    target: { value: "RELIANCE" },
  });
  await screen.findByRole("option", { name: "2099-10-29" });
  fireEvent.change(screen.getByLabelText("Expiry"), {
    target: { value: "2099-10-29" },
  });
  await screen.findByRole("option", { name: "CE" });
  fireEvent.change(screen.getByLabelText("Option type"), {
    target: { value: "CE" },
  });
  await screen.findByRole("option", { name: "1400" });
  fireEvent.change(screen.getByLabelText("Strike"), {
    target: { value: "1400" },
  });
  await waitFor(() =>
    expect(params(fetch.mock.calls.at(-1)![0]).get("strike")).toBe("1400"),
  );
  const q = params(fetch.mock.calls.at(-1)![0]);
  expect(Object.fromEntries(q)).toEqual({
    asset: "options",
    underlying: "RELIANCE",
    expiry: "2099-10-29",
    option_type: "CE",
    strike: "1400",
    page: "1",
  });
  await screen.findByRole("option", { name: "2099-11-26" });
  fireEvent.change(screen.getByLabelText("Expiry"), {
    target: { value: "2099-11-26" },
  });
  await waitFor(() =>
    expect(params(fetch.mock.calls.at(-1)![0]).get("expiry")).toBe(
      "2099-11-26",
    ),
  );
  expect(params(fetch.mock.calls.at(-1)![0]).has("option_type")).toBe(false);
  expect(params(fetch.mock.calls.at(-1)![0]).has("strike")).toBe(false);
  fireEvent.click(screen.getByRole("radio", { name: "Futures" }));
  expect(screen.queryByLabelText("Strike")).toBeNull();
  expect(screen.getByLabelText("Expiry")).toBeDisabled();
  await waitFor(() =>
    expect(params(fetch.mock.calls.at(-1)![0]).get("asset")).toBe("futures"),
  );
  expect(params(fetch.mock.calls.at(-1)![0]).has("underlying")).toBe(false);
});

test.each(["Reliance Industries Limited", null])(
  "equity cards use provider name %s without exposing tokens or inventing names",
  async (name) => {
    vi.spyOn(global, "fetch").mockImplementation(async () =>
      Response.json({
        ...empty,
        total: 1,
        instruments: [{ ...equity, name }],
      }),
    );
    open();
    fireEvent.change(screen.getByLabelText("Search stock"), {
      target: { value: "Reliance Industries Ltd" },
    });
    await screen.findByRole("button", { name: "Buy RELIANCE" });
    expect(screen.getByText("NSE · Equity")).toBeVisible();
    if (name) expect(screen.getByText(name)).toBeVisible();
    else expect(screen.queryByText(/Industries/)).toBeNull();
    expect(screen.queryByText(/^Token /)).toBeNull();
    expect(screen.queryByText(/Segment NSE/)).toBeNull();
    expect(screen.getByText("Reference / LTP: —")).toBeVisible();
    expect(screen.getByRole("button", { name: "Sell RELIANCE" })).toBeEnabled();
  },
);
