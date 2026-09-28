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
};
const cap: Capability = {
  enabled: true,
  instrument,
  products: ["NRML", "MIS"],
  quantity_unit: "lots",
  max_quantity: 1000000,
  order_types: [
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
function mock(fail = false) {
  return vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    if (String(url).includes("capabilities")) return Response.json(cap);
    if (String(url).endsWith("preview")) return Response.json(intent);
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
