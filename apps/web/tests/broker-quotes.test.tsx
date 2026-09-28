import {
  act,
  fireEvent,
  render,
  renderHook,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { OrderTicket } from "../src/components/brokers/order-ticket";
import { quotePrice, useBrokerQuotes } from "../src/lib/broker-quotes";
import type { Account, Instrument } from "../src/lib/brokers";
const navigation = vi.hoisted(() => ({
  path: "/brokers/accounts/account/orders",
}));
vi.mock("next/navigation", () => ({ usePathname: () => navigation.path }));
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
  reference: "ZERODHA:NSE:RELIANCE",
  native_token: "11",
  symbol: "RELIANCE",
  exchange: "NSE",
  kind: "EQ",
  segment: "NSE",
  tick_size: "0.05",
  lot_size: "1",
};
const batch = (
  price: string | null = "111.05",
  item = instrument,
  age = 0,
) => ({
  received_at: new Date(Date.now() - age).toISOString(),
  quotes: [
    { reference: item.reference, native_token: item.native_token, price },
  ],
});
const advance = async (ms = 1) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
};
beforeEach(() => {
  vi.useFakeTimers();
  navigation.path = "/brokers/accounts/account/orders";
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function setup(
  options: {
    deferred?: Promise<Response>;
    market?: boolean;
    item?: Instrument;
  } = {},
) {
  let price: string | null = "111.05";
  let age = 0;
  let failed = false;
  let first = true;
  const item = options.item || instrument;
  const fetch = vi
    .spyOn(global, "fetch")
    .mockImplementation(async (url, init) => {
      if (String(url).includes("capabilities"))
        return Response.json({
          enabled: true,
          instrument: item,
          products: ["CNC"],
          quantity_unit: "shares",
          max_quantity: 10000,
          order_types: [
            {
              name: options.market ? "MARKET" : "LIMIT",
              price_required: !options.market,
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
        });
      if (String(url).endsWith("quotes")) {
        if (first && options.deferred) {
          first = false;
          return options.deferred;
        }
        if (failed) throw new Error("provider unavailable");
        return Response.json(batch(price, item, age));
      }
      if (String(url).endsWith("preview"))
        return Response.json({
          id: "intent",
          account_id: account.id,
          account_name: account.name,
          instrument: item,
          order: JSON.parse(String(init?.body)),
          status: "PREVIEWED",
          estimated_value: "100",
          estimated_margin: null,
          available_cash: null,
        });
      throw new Error(String(url));
    });
  const view = render(
    <OrderTicket
      account={account}
      initial={{ instrument: item, side: "BUY" }}
      close={() => {}}
    />,
  );
  return {
    ...view,
    fetch,
    update: (v: string | null, a = 0) => {
      price = v;
      age = a;
    },
    fail: () => {
      failed = true;
    },
  };
}

test("first LTP initializes once, explicit Set Price and manual edits win; preview uses frozen price", async () => {
  const app = setup();
  await advance();
  const input = screen.getByLabelText("Price (₹)");
  expect(input).toHaveValue(111.05);
  app.update("112.10");
  await advance(2000);
  expect(screen.getByTestId("reference-ltp")).toHaveTextContent("112.1");
  expect(input).toHaveValue(111.05);
  fireEvent.click(screen.getByRole("button", { name: "Set Price" }));
  expect(input).toHaveValue(112.1);
  fireEvent.change(input, { target: { value: "125.05" } });
  app.update("113.15");
  await advance(2000);
  expect(input).toHaveValue(125.05);
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  await advance();
  const request = app.fetch.mock.calls.find((c) =>
    String(c[0]).endsWith("preview"),
  )!;
  expect(JSON.parse(String(request[1]?.body)).price).toBe("125.05");
  const count = app.fetch.mock.calls.length;
  await advance(10000);
  expect(app.fetch.mock.calls).toHaveLength(count);
});

test.each([false, true])(
  "delayed first quote respects price dirty state %s",
  async (dirty) => {
    let resolve!: (r: Response) => void;
    const app = setup({
      deferred: new Promise((r) => {
        resolve = r;
      }),
    });
    await advance();
    const input = screen.getByLabelText("Price (₹)");
    expect(input).toHaveValue(null);
    expect(screen.getByRole("button", { name: "Set Price" })).toBeDisabled();
    if (dirty) fireEvent.change(input, { target: { value: "99.05" } });
    await act(async () => resolve(Response.json(batch())));
    await advance();
    expect(input).toHaveValue(dirty ? 99.05 : 111.05);
    app.unmount();
  },
);

test("unknown, stale, invalid-tick and failed quotes cannot be copied or overwrite Price", async () => {
  const app = setup();
  await advance();
  app.update(null);
  await advance(2000);
  expect(screen.getByTestId("reference-ltp")).toHaveTextContent("—");
  expect(screen.getByRole("button", { name: "Set Price" })).toBeDisabled();
  app.update("123.00", 6000);
  await advance(2000);
  expect(screen.getByRole("button", { name: "Set Price" })).toBeDisabled();
  app.update("123.03");
  await advance(2000);
  expect(screen.getByTestId("reference-ltp")).toHaveTextContent("123.03");
  expect(screen.getByRole("button", { name: "Set Price" })).toBeDisabled();
  app.fail();
  await advance(2000);
  expect(screen.getByTestId("reference-ltp")).toHaveTextContent("—");
  expect(screen.getByLabelText("Price (₹)")).toHaveValue(111.05);
});

test("MARKET capability stays reference-only and SL trigger is never initialized", async () => {
  const app = setup({ market: true });
  await advance();
  expect(screen.getByTestId("reference-ltp")).toHaveTextContent("111.05");
  expect(screen.queryByLabelText("Price (₹)")).toBeNull();
  expect(screen.queryByRole("button", { name: "Set Price" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Preview Buy" }));
  await advance();
  const call = app.fetch.mock.calls.find((c) =>
    String(c[0]).endsWith("preview"),
  )!;
  expect(JSON.parse(String(call[1]?.body))).not.toHaveProperty("price");
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  await advance();
  fireEvent.change(screen.getByLabelText("Order type"), {
    target: { value: "SL" },
  });
  await advance();
  expect(screen.getByLabelText(/Broker trigger price/)).toHaveValue(null);
  expect(screen.getByLabelText("Stop Loss Price")).toBeDisabled();
  expect(screen.getByLabelText("Take Profit Price")).toBeDisabled();
});

test.each(["FUT", "CE"])(
  "%s requests the selected native contract, never underlying spot",
  async (kind) => {
    const item = {
      ...instrument,
      reference: `ZERODHA:NFO:RELIANCE${kind}`,
      native_token: kind === "FUT" ? "22" : "23",
      symbol: `RELIANCE${kind}`,
      exchange: "NFO",
      kind,
      underlying: "RELIANCE",
    };
    const app = setup({ item });
    await advance();
    const call = app.fetch.mock.calls.find((c) =>
      String(c[0]).endsWith("quotes"),
    )!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({
      instruments: [
        { reference: item.reference, native_token: item.native_token },
      ],
    });
  },
);

test("polling is serial, replaced identities abort old work, unmount clears timers and late results", async () => {
  const requests: {
    signal: AbortSignal;
    resolve: (r: Response) => void;
    body: unknown;
  }[] = [];
  vi.spyOn(global, "fetch").mockImplementation(
    (_url, init) =>
      new Promise((resolve) =>
        requests.push({
          signal: init?.signal as AbortSignal,
          resolve,
          body: JSON.parse(String(init?.body)),
        }),
      ),
  );
  const hook = renderHook(
    ({ items }) => useBrokerQuotes("accounts/a/order-entry/", items),
    { initialProps: { items: [instrument] } },
  );
  await advance(500);
  expect(requests).toHaveLength(1);
  const second = {
    ...instrument,
    reference: "ZERODHA:BSE:RELIANCE",
    native_token: "12",
  };
  hook.rerender({ items: [second] });
  await advance();
  expect(requests[0].signal.aborted).toBe(true);
  expect(requests).toHaveLength(2);
  await act(async () => requests[0].resolve(Response.json(batch())));
  expect(hook.result.current).toEqual({});
  await act(async () =>
    requests[1].resolve(Response.json(batch("120", second))),
  );
  await advance(2000);
  expect(requests).toHaveLength(3);
  await advance(1000);
  expect(requests).toHaveLength(3); // no overlapping request
  hook.unmount();
  expect(requests[2].signal.aborted).toBe(true);
  await act(async () =>
    requests[2].resolve(Response.json(batch("121", second))),
  );
  await advance(10000);
  expect(requests).toHaveLength(3);
  expect(vi.getTimerCount()).toBe(0);
});

test("decimal tick alignment is exact and never silently rounded", () => {
  const q = {
    ...batch("0.15").quotes[0],
    native_token: "11",
    received_at: new Date().toISOString(),
  };
  expect(quotePrice(q, "0.05")).toBe("0.15");
  expect(quotePrice({ ...q, price: "0.16" }, "0.05")).toBeNull();
  expect(quotePrice({ ...q, price: "0" }, "0.05")).toBeNull();
});

test("only intersecting result cards are batched; refresh, failure, scrolling and class changes replace scope", async () => {
  let intersection: IntersectionObserverCallback;
  const observed: Element[] = [];
  const disconnect = vi.fn();
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: IntersectionObserverCallback) {
        intersection = callback;
      }
      observe(node: Element) {
        observed.push(node);
        intersection(
          [
            {
              target: node,
              isIntersecting:
                Number((node as HTMLElement).dataset.quoteIndex) < 2,
            } as IntersectionObserverEntry,
          ],
          this as unknown as IntersectionObserver,
        );
      }
      disconnect = disconnect;
    },
  );
  const items = [
    instrument,
    {
      ...instrument,
      symbol: "SECOND",
      reference: "ZERODHA:NSE:SECOND",
      native_token: "12",
    },
    {
      ...instrument,
      symbol: "OFFSCREEN",
      reference: "ZERODHA:NSE:OFFSCREEN",
      native_token: "13",
    },
  ];
  let price = "100";
  let failed = false;
  const fetch = vi
    .spyOn(global, "fetch")
    .mockImplementation(async (url, init) => {
      if (String(url).includes("choices"))
        return Response.json({
          underlyings: [],
          expiries: [],
          option_types: [],
          strikes: [],
          instruments: items,
          total: 3,
          page: 1,
        });
      if (failed) throw new Error("unavailable");
      const selected = JSON.parse(String(init?.body)).instruments as {
        reference: string;
        native_token: string;
      }[];
      return Response.json({
        received_at: new Date().toISOString(),
        quotes: selected.map((i) => ({ ...i, price })),
      });
    });
  const app = render(<OrderTicket account={account} close={() => {}} />);
  await advance(200);
  await advance();
  const quoteCalls = () =>
    fetch.mock.calls.filter((c) => String(c[0]).endsWith("quotes"));
  expect(JSON.parse(String(quoteCalls()[0][1]?.body)).instruments).toHaveLength(
    2,
  );
  expect(
    JSON.parse(String(quoteCalls()[0][1]?.body)).instruments.map(
      (i: Instrument) => i.native_token,
    ),
  ).toEqual(["11", "12"]);
  expect(
    screen.getAllByTestId("reference-ltp").map((e) => e.textContent),
  ).toEqual([
    "Reference / LTP: ₹ 100",
    "Reference / LTP: ₹ 100",
    "Reference / LTP: —",
  ]);
  price = "101";
  await advance(2000);
  expect(screen.getAllByTestId("reference-ltp")[0]).toHaveTextContent("₹ 101");
  failed = true;
  await advance(2000);
  expect(screen.getAllByTestId("reference-ltp")[0]).toHaveTextContent("—");
  failed = false;
  act(() =>
    intersection(
      [
        { target: observed[0], isIntersecting: false },
        { target: observed[2], isIntersecting: true },
      ] as IntersectionObserverEntry[],
      {} as IntersectionObserver,
    ),
  );
  await advance();
  expect(
    JSON.parse(String(quoteCalls().at(-1)![1]?.body)).instruments.map(
      (i: Instrument) => i.native_token,
    ),
  ).toEqual(["13", "12"]); // sorted by reference
  fireEvent.click(screen.getByRole("radio", { name: "Futures" }));
  const count = quoteCalls().length;
  await advance(50);
  expect(quoteCalls()).toHaveLength(count);
  app.unmount();
  await advance(10000);
  expect(quoteCalls()).toHaveLength(count);
  expect(disconnect).toHaveBeenCalled();
});

test("freshness expires independently of the next poll", async () => {
  vi.spyOn(global, "fetch").mockResolvedValue(
    Response.json(batch("100", instrument, 4500)),
  );
  const hook = renderHook(() =>
    useBrokerQuotes("accounts/a/order-entry/", [instrument]),
  );
  await advance();
  expect(Object.keys(hook.result.current)).toHaveLength(1);
  await advance(501);
  expect(hook.result.current).toEqual({});
});

test("route changes stop quotes and close the ticket", async () => {
  const app = setup();
  await advance();
  const close = vi.fn();
  navigation.path = "/brokers/accounts/account/holdings";
  app.rerender(
    <OrderTicket
      account={account}
      initial={{ instrument, side: "BUY" }}
      close={close}
    />,
  );
  expect(close).toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).toBeNull();
  const count = app.fetch.mock.calls.length;
  await advance(10000);
  expect(app.fetch.mock.calls).toHaveLength(count);
});

test("launch-card quote initializes the ticket even when its next quote has moved", async () => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      callback: IntersectionObserverCallback;
      constructor(callback: IntersectionObserverCallback) {
        this.callback = callback;
      }
      observe(node: Element) {
        this.callback(
          [{ target: node, isIntersecting: true } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }
      disconnect() {}
    },
  );
  let calls = 0;
  vi.spyOn(global, "fetch").mockImplementation(async (url) => {
    if (String(url).includes("choices"))
      return Response.json({
        underlyings: [],
        expiries: [],
        option_types: [],
        strikes: [],
        instruments: [instrument],
        total: 1,
        page: 1,
      });
    if (String(url).includes("capabilities"))
      return Response.json({
        enabled: true,
        instrument,
        products: ["CNC"],
        quantity_unit: "shares",
        max_quantity: 1000,
        order_types: [
          {
            name: "LIMIT",
            price_required: true,
            trigger_required: false,
            validities: ["DAY"],
          },
        ],
      });
    calls++;
    return Response.json(batch(calls === 1 ? "100" : "105"));
  });
  render(<OrderTicket account={account} close={() => {}} />);
  await advance(200);
  await advance();
  expect(screen.getByTestId("reference-ltp")).toHaveTextContent("₹ 100");
  fireEvent.click(screen.getByRole("button", { name: "Buy RELIANCE" }));
  await advance();
  expect(screen.getByTestId("reference-ltp")).toHaveTextContent("₹ 105");
  expect(screen.getByLabelText("Price (₹)")).toHaveValue(100);
});
