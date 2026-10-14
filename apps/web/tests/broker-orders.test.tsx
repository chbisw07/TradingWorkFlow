import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { OrderTicket } from "../src/components/brokers/order-ticket";
import type { Account, Instrument } from "../src/lib/brokers";
import {
  canOrder,
  type Capability,
  type Intent,
} from "../src/lib/broker-orders";
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
const instrument: Instrument = {
  symbol: "NIFTYCE",
  exchange: "NFO",
  reference: "ZERODHA:NFO:NIFTYCE",
  native_token: "123",
  kind: "CE",
  segment: "NFO-OPT",
  underlying: "NIFTY",
  expiry: "2026-12-31",
  strike: "25000",
  lot_size: "65",
  tick_size: "0.05",
  canonical_id: "NFO:NIFTY:2026-12-31:25000:CE",
  underlying_type: "INDEX",
  option_type: "CE",
  currency: "INR",
  is_active: true,
  last_trading_date: "2026-12-31",
};
const cap: Capability = {
  enabled: true,
  instrument,
  products: ["NRML", "MIS"],
  quantity_unit: "lots",
  max_quantity: 1000000,
  broker: {
    supports_equity: true,
    supports_futures: true,
    supports_options: true,
    option_buy_supported: true,
    option_sell_supported: true,
    intraday_product_support: true,
    overnight_product_support: true,
  },
  order_types: [
    {
      name: "MARKET",
      price_required: false,
      trigger_required: false,
      validities: ["DAY", "IOC"],
    },
    {
      name: "LIMIT",
      price_required: true,
      trigger_required: false,
      validities: ["DAY"],
    },
    {
      name: "SL",
      price_required: true,
      trigger_required: true,
      validities: ["DAY"],
    },
  ],
};
const intent: Intent = {
  id: "intent",
  account_id: account.id,
  account_name: account.name,
  instrument,
  order: {
    reference: instrument.reference,
    native_token: "123",
    side: "BUY",
    product: "NRML",
    order_type: "LIMIT",
    quantity: 130,
    lots: 2,
    price: "100",
    trigger_price: null,
    validity: "DAY",
  },
  status: "PREVIEWED",
  created_at: "",
  expires_at: "",
  broker_order_id: null,
  provider_status: null,
  failure: null,
  instrument_type: "OPTION",
  option_contract: {
    canonical_id: "NFO:NIFTY:2026-12-31:25000:CE",
    exchange: "NFO",
    segment: "NFO-OPT",
    underlying_symbol: "NIFTY",
    underlying_type: "INDEX",
    expiry: "2026-12-31",
    strike: "25000",
    option_type: "CE",
    lot_size: 65,
    display_symbol: "NIFTY 31-DEC-2026 25000 CE",
    tick_size: "0.05",
    freeze_quantity: null,
    contract_multiplier: null,
    currency: "INR",
    is_active: true,
    last_trading_date: "2026-12-31",
  },
  broker_option_mapping: {
    provider: "zerodha",
    canonical_id: "NFO:NIFTY:2026-12-31:25000:CE",
    exchange: "NFO",
    trading_symbol: "NIFTYCE",
    native_token: "123",
    reference: "ZERODHA:NFO:NIFTYCE",
    lot_size: 65,
    tick_size: "0.05",
    resolved_at: "2026-10-09T12:00:00Z",
    master_version: null,
  },
  warnings: [],
  reference_price: "100",
  premium_outlay: "13000",
  margin_status: "UNAVAILABLE",
  estimated_value: "13000",
  estimated_margin: null,
  available_cash: null,
};
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});
afterEach(() => vi.restoreAllMocks());
function mock(
  fail = false,
  previewIntent: Intent = intent,
  capability: Capability = cap,
) {
  return vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    if (String(url).includes("capabilities")) return Response.json(capability);
    if (String(url).endsWith("preview")) return Response.json(previewIntent);
    if (String(url).endsWith("confirm")) {
      if (fail) throw new Error("network");
      return Response.json({
        ...intent,
        status: "SUBMITTED",
        broker_order_id: "order123",
      });
    }
    if (String(url).endsWith("reconcile"))
      return Response.json({
        ...intent,
        status: "SUBMITTED",
        broker_order_id: "order123",
        provider_status: "OPEN",
      });
    throw new Error(String(url));
  });
}
async function fill() {
  await screen.findByLabelText("Lots");
  fireEvent.change(screen.getByLabelText("Lots"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Price (₹)"), {
    target: { value: "100" },
  });
}
test("lots are auto converted, managed exits disabled and preview precedes one explicit confirmation", async () => {
  const fetch = mock();
  render(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "BUY" }}
      close={() => {}}
    />,
  );
  await fill();
  expect(screen.getByText("130")).toBeVisible();
  for (const label of [
    "Stop Loss Price",
    "Stop Loss Percent",
    "Take Profit Price",
    "Take Profit Percent",
  ])
    expect(screen.getByLabelText(label)).toBeDisabled();
  expect(screen.getByText("Estimated margin").nextSibling).toHaveTextContent(
    "—",
  );
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  await screen.findByRole("button", { name: "Confirm Buy" });
  const call = fetch.mock.calls.find((c) => String(c[0]).endsWith("preview"))!;
  expect(JSON.parse(String(call[1]?.body))).toEqual(intent.order);
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("confirm")),
  ).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Confirm Buy" }));
  await screen.findByRole("heading", { name: "Order Submitted" });
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("confirm")),
  ).toHaveLength(1);
  expect(screen.getByRole("link", { name: "View in Orders" })).toHaveAttribute(
    "href",
    "/brokers/accounts/account/orders",
  );
});
test("unknown submission hides another-order action and recovery only reads broker truth", async () => {
  const fetch = mock(true);
  render(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "BUY" }}
      close={() => {}}
    />,
  );
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  fireEvent.click(await screen.findByRole("button", { name: "Confirm Buy" }));
  await screen.findByRole("heading", { name: "Submission status uncertain" });
  expect(
    screen.queryByRole("button", { name: "Place Another Order" }),
  ).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh broker status" }),
  );
  await screen.findByRole("heading", { name: "Order Submitted" });
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("confirm")),
  ).toHaveLength(1);
});
test("broker trigger belongs to SL only and is separate from the disabled exit plan", async () => {
  mock();
  render(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "SELL" }}
      close={() => {}}
    />,
  );
  await fill();
  expect(screen.queryByLabelText(/Broker trigger/)).toBeNull();
  fireEvent.change(screen.getByLabelText("Order type"), {
    target: { value: "SL" },
  });
  expect(screen.getByLabelText(/Broker trigger/)).toBeEnabled();
  expect(screen.getByLabelText("Stop Loss Price")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Preview Sell" })).toBeEnabled();
});
test("same intent cannot be submitted twice while confirmation is pending", async () => {
  const fetch = mock();
  let resolve: (r: Response) => void = () => {};
  render(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "BUY" }}
      close={() => {}}
    />,
  );
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  const button = await screen.findByRole("button", { name: "Confirm Buy" });
  fetch.mockImplementationOnce(
    () =>
      new Promise<Response>((r) => {
        resolve = r;
      }),
  );
  fireEvent.click(button);
  fireEvent.click(button);
  expect(
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("confirm")),
  ).toHaveLength(1);
  expect(button).toBeDisabled();
  resolve(
    Response.json({ ...intent, status: "SUBMITTED", broker_order_id: "123" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("heading", { name: "Order Submitted" }),
    ).toBeVisible(),
  );
});

test("Instruments actions exclude expired, unsupported and incomplete contracts", () => {
  const valid = { ...instrument, expiry: "2099-12-31" };
  expect(canOrder(valid)).toBe(true);
  expect(canOrder({ ...valid, expiry: "2000-01-01" })).toBe(false);
  expect(canOrder({ ...valid, exchange: "MCX" })).toBe(false);
  expect(canOrder({ ...valid, tick_size: null })).toBe(false);
  expect(canOrder({ ...valid, lot_size: "1.5" })).toBe(false);
});

test("option MARKET preview omits price and shows exact contract plus short-risk warning", async () => {
  const marketIntent: Intent = {
    ...intent,
    order: {
      ...intent.order,
      side: "SELL",
      order_type: "MARKET",
      price: undefined,
    },
    warnings: [
      "Short option positions may have substantial or theoretically unbounded risk.",
    ],
    reference_price: "101.25",
    estimated_value: "13162.5",
    premium_outlay: null,
    estimated_margin: null,
    margin_status: "UNAVAILABLE",
  };
  const fetch = mock(false, marketIntent);
  render(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "SELL", orderType: "MARKET" }}
      close={() => {}}
    />,
  );
  await screen.findByLabelText("Lots");
  expect(screen.queryByLabelText("Price (₹)")).toBeNull();
  expect(screen.getByLabelText("Order type")).toHaveValue("MARKET");
  fireEvent.change(screen.getByLabelText("Lots"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Preview Sell" }));
  await screen.findByRole("button", { name: "Confirm Sell" });

  const call = fetch.mock.calls.find((entry) =>
    String(entry[0]).endsWith("preview"),
  )!;
  const submitted = JSON.parse(String(call[1]?.body));
  expect(submitted).toMatchObject({
    side: "SELL",
    order_type: "MARKET",
    quantity: 130,
    lots: 2,
  });
  expect(submitted).not.toHaveProperty("price");
  expect(screen.getByText("NIFTY 31 Dec 2026 25000 CE")).toBeVisible();
  expect(screen.getByText("Underlying").nextSibling).toHaveTextContent("NIFTY");
  expect(screen.getByText("Price").nextSibling).toHaveTextContent("Market");
  expect(screen.getByText("Estimated margin").nextSibling).toHaveTextContent(
    "Margin estimate unavailable",
  );
  expect(screen.getByRole("note")).toHaveTextContent("Short option positions");
  expect(
    fetch.mock.calls.filter((entry) => String(entry[0]).endsWith("confirm")),
  ).toHaveLength(0);
});

test("TWF destination reuses ticket and server preview, creates once, and never confirms broker intent", async () => {
  const preview = {
    preview_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    expires_at: "2026-10-14T12:05:00Z",
    instrument: {
      asset_class: "OPTION",
      instrument_id: "11111111-1111-4111-8111-111111111111",
      exchange: "NFO",
      symbol: "NIFTY 2026-12-31 25000 CE",
      underlying_id: "22222222-2222-4222-8222-222222222222",
      expiry: "2026-12-31",
      strike: "25000",
      option_type: "CE",
      lot_size: 65,
      tick_size: "0.05",
    },
    terms: {
      side: "BUY",
      quantity: 130,
      order_type: "LIMIT",
      limit_price: "100",
      product: "CARRY_FORWARD",
      validity: "DAY",
    },
    source: "MANUAL",
    account_id: account.id,
  };
  let complete: (response: Response) => void = () => {};
  const fetch = vi
    .spyOn(global, "fetch")
    .mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.includes("capabilities")) return Response.json(cap);
      if (path.endsWith("/twf-orders/preview")) return Response.json(preview);
      if (path.endsWith("/twf-orders"))
        return new Promise<Response>((resolve) => {
          complete = resolve;
        });
      throw new Error(`Unexpected broker request: ${path} ${init?.method}`);
    });
  const created = vi.fn();
  render(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "BUY" }}
      destination="TWF_ORDER"
      onCreated={created}
      close={() => {}}
    />,
  );
  await fill();
  expect(screen.queryByRole("option", { name: "SL" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  await screen.findByText(/No broker order will be submitted/);
  expect(screen.getByText("2026-12-31")).toBeVisible();
  const previewCall = fetch.mock.calls.find(([url]) =>
    String(url).endsWith("/twf-orders/preview"),
  );
  expect(previewCall).toBeDefined();
  expect(JSON.parse(String(previewCall?.[1]?.body))).toMatchObject({
    account_id: account.id,
    reference: instrument.reference,
    native_token: "123",
    side: "BUY",
    quantity: 130,
  });
  const button = screen.getByRole("button", { name: "Create TWF Order" });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(
    fetch.mock.calls.filter(([url]) => String(url).endsWith("/twf-orders")),
  ).toHaveLength(1);
  expect(button).toBeDisabled();
  const createCall = fetch.mock.calls.find(([url]) =>
    String(url).endsWith("/twf-orders"),
  );
  expect(JSON.parse(String(createCall?.[1]?.body)).preview_id).toBe(
    preview.preview_id,
  );
  complete(
    Response.json({
      order: {
        twf_order_id: "33333333-3333-4333-8333-333333333333",
        state: "READY",
        terms: preview.terms,
        instrument: preview.instrument,
        created_at: "2026-10-14T12:00:00Z",
      },
      validation: { ready: true, violations: [], order_version: 2 },
    }),
  );
  await screen.findByRole("heading", { name: "TWF Order Created" });
  expect(created).toHaveBeenCalledWith("33333333-3333-4333-8333-333333333333");
  expect(
    fetch.mock.calls.some(([url]) => String(url).includes("/confirm")),
  ).toBe(false);
  expect(
    screen.getByRole("link", { name: "View Order Details" }),
  ).toHaveAttribute(
    "href",
    "/orders?selected=33333333-3333-4333-8333-333333333333",
  );
});

test("TWF binding rejection returns ticket to a fresh Preview", async () => {
  let previewCount = 0;
  const fetch = vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    const path = String(url);
    if (path.includes("capabilities")) return Response.json(cap);
    if (path.endsWith("/twf-orders/preview")) {
      previewCount++;
      return Response.json({
        preview_id: `aaaaaaaa-aaaa-4aaa-8aaa-${String(previewCount).padStart(12, "0")}`,
        expires_at: "2026-10-14T12:05:00Z",
        instrument: {
          asset_class: "OPTION",
          instrument_id: "11111111-1111-4111-8111-111111111111",
          exchange: "NFO",
          symbol: "NIFTY 2026-12-31 25000 CE",
          underlying_id: "22222222-2222-4222-8222-222222222222",
          expiry: "2026-12-31",
          strike: "25000",
          option_type: "CE",
          lot_size: 65,
          tick_size: "0.05",
        },
        terms: {
          side: "BUY",
          quantity: 130,
          order_type: "LIMIT",
          limit_price: "100",
          product: "CARRY_FORWARD",
          validity: "DAY",
        },
        source: "MANUAL",
        account_id: account.id,
      });
    }
    if (path.endsWith("/twf-orders"))
      return Response.json(
        { error: { code: "PREVIEW_MISMATCH", message: "Changed" } },
        { status: 409 },
      );
    throw new Error(`Unexpected request: ${path}`);
  });
  render(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "BUY" }}
      destination="TWF_ORDER"
      close={() => {}}
    />,
  );
  await fill();
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  await screen.findByRole("button", { name: "Create TWF Order" });
  fireEvent.click(screen.getByRole("button", { name: "Create TWF Order" }));
  await screen.findByText(/Please review again/);
  expect(screen.queryByRole("button", { name: "Create TWF Order" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  await screen.findByRole("button", { name: "Create TWF Order" });
  expect(previewCount).toBe(2);
  expect(
    fetch.mock.calls.filter(([url]) => String(url).endsWith("/twf-orders")),
  ).toHaveLength(1);
});
