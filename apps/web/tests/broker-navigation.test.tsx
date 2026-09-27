import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BrokerLinks } from "../src/components/brokers/broker-navigation";
import { RealBrokers } from "../src/components/brokers/real-brokers";
import { BrokerRoster } from "../src/components/brokers/real-broker-room";
import { brokerFixture } from "./broker-fixtures";

afterEach(() => vi.unstubAllGlobals());

test("real broker destinations are primary; synthetic accounts load only after disclosure", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json(brokerFixture())));
  vi.stubGlobal("fetch", fetcher);
  render(<BrokerLinks active="zerodha" />);
  const nav = screen.getByRole("navigation", { name: "Broker workspace" });
  expect(
    within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent),
  ).toEqual(["Overview", "Zerodha", "Manage Brokers"]);
  expect(within(nav).getByRole("link", { name: "Zerodha" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(
    screen.getByRole("combobox", { name: "Broker workspace" }),
  ).toHaveValue("/brokers/zerodha");
  expect(fetcher).not.toHaveBeenCalled();
  expect(screen.queryByRole("link", { name: /Alpha/ })).toBeNull();
  fireEvent.click(
    screen.getByText("Development / Synthetic", { selector: "summary" }),
  );
  await screen.findByRole("link", { name: /Alpha A1/ });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(within(nav).queryByRole("link", { name: /Alpha/ })).toBeNull();
});

test("normal overview has no synthetic data requests and offers a setup action", async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json([]));
  vi.stubGlobal("fetch", fetcher);
  render(
    <>
      <BrokerLinks />
      <BrokerRoster />
    </>,
  );
  expect(
    await screen.findByRole("link", { name: "Configure Zerodha" }),
  ).toHaveAttribute("href", "/brokers/manage");
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    "/api/v1/broker-auth/accounts",
  ]);
  expect(screen.queryByText("Analytical position aggregate")).toBeNull();
});

test("unsupported providers have no actions and new account setup remains available", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(Response.json([])));
  vi.stubGlobal("fetch", fetcher);
  render(<RealBrokers />);
  await screen.findByRole("button", { name: "Add Zerodha account" });
  const add = screen
    .getByRole("button", { name: "Add Zerodha account" })
    .closest("details")!;
  add.open = false;
  fireEvent.click(screen.getByRole("button", { name: "Configure Zerodha" }));
  expect(add.open).toBe(true);
  expect(screen.getByLabelText("Account label")).toHaveFocus();
  for (const name of ["Fyers", "Angel One"]) {
    const card = screen.getByRole("heading", { name }).closest("article")!;
    expect(card).toHaveTextContent("Coming later");
    expect(within(card).queryByRole("button")).toBeNull();
    expect(within(card).queryByRole("link")).toBeNull();
  }
  fireEvent.click(screen.getByRole("button", { name: "Add Zerodha account" }));
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(([url]) => url.endsWith("create-account")),
    ).toBe(true),
  );
});
