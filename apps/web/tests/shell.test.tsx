import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { AppShell } from "../src/components/shell/app-shell";
import { SurfaceState, stateLabels } from "../src/components/ui/surface-state";
import ErrorView from "../src/app/error";
import NotFound from "../src/app/not-found";
import Home from "../src/app/(protected)/page";
import Loading from "../src/app/loading";

const location = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({
  usePathname: () => location.pathname,
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

beforeEach(() => {
  location.pathname = "/";
  window.history.replaceState(null, "", "/");
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  );
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});

test("shell renders product, semantic regions, target, and honest service states", () => {
  render(
    <AppShell>
      <Home />
    </AppShell>,
  );
  expect(
    screen.getByRole("link", { name: "TradingWorkFlow home" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("main")).toHaveTextContent("TWF-1.1 Frontend Shell");
  expect(screen.getByRole("banner")).toHaveTextContent("Not signed in");
  expect(screen.getByRole("contentinfo")).toHaveTextContent(
    "© 2026 TradingWorkFlow",
  );
  expect(screen.getByRole("search")).toBeInTheDocument();
  expect(screen.getByLabelText("Search symbol — coming later")).toBeDisabled();
  expect(
    screen.getByLabelText("Market summary — live values unavailable"),
  ).toHaveTextContent("NIFTY");
  expect(screen.getAllByText("Unavailable")).toHaveLength(3);
  expect(
    screen.getByRole("region", { name: "System console" }),
  ).toBeInTheDocument();
  const aside = screen.getByRole("complementary", {
    name: "Workspace context",
  });
  expect(
    within(aside).getByRole("button", { name: "Check service status" }),
  ).toBeEnabled();
  expect(aside).toHaveTextContent("Configured services have not been checked.");
});

test("sidebar matches the approved groups and route mappings", () => {
  render(
    <AppShell>
      <Home />
    </AppShell>,
  );
  const nav = screen.getByRole("navigation", { name: "Primary navigation" });
  expect(
    within(nav)
      .getAllByRole("heading")
      .map((el) => el.textContent),
  ).toEqual(["WORKSPACE", "TOOLS", "INSIGHTS", "SETTINGS"]);
  expect(
    within(nav)
      .getAllByRole("link")
      .map((el) => el.textContent),
  ).toEqual([
    "Home",
    "Brokers",
    "Market Overview",
    "Scanners",
    "Discovery",
    "Watchlists",
    "Positions",
    "Orders",
    "Alerts",
    "Options Analytics",
    "Strategy Builder",
    "Risk & Greeks",
    "Market Intelligence",
    "News & Events",
    "Preferences",
    "Integrations",
    "Advanced",
  ]);
  expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(within(nav).getByRole("link", { name: "Brokers" })).toHaveAttribute(
    "href",
    "/brokers",
  );
  expect(within(nav).getByRole("link", { name: "Discovery" })).toHaveAttribute(
    "href",
    "/candidates",
  );
  expect(
    within(nav).getByRole("link", { name: "Integrations" }),
  ).toHaveAttribute("href", "/settings#integrations");
  expect(within(nav).getByRole("link", { name: "Advanced" })).toHaveAttribute(
    "href",
    "/settings#advanced",
  );
});

test.each([
  ["/brokers", "Brokers"],
  ["/brokers/accounts/example/orders", "Brokers"],
  ["/scanners", "Scanners"],
  ["/candidates", "Discovery"],
  ["/settings", "Preferences"],
])("only the correct route is active at %s", (pathname, label) => {
  location.pathname = pathname;
  render(
    <AppShell>
      <p>Existing workspace</p>
    </AppShell>,
  );
  const nav = screen.getByRole("navigation", { name: "Primary navigation" });
  const active = within(nav)
    .getAllByRole("link")
    .filter((el) => el.getAttribute("aria-current") === "page");
  expect(active).toHaveLength(1);
  expect(active[0]).toHaveTextContent(label);
});

test("mobile navigation opens a modal and closes after navigation", () => {
  render(
    <AppShell>
      <Home />
    </AppShell>,
  );
  const toggle = screen.getByRole("button", { name: "Workspace navigation" });
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const dialog = screen.getByRole("dialog", { name: "Workspace navigation" });
  const scannerLink = within(dialog).getByRole("link", { name: "Scanners" });
  scannerLink.addEventListener("click", (event) => event.preventDefault());
  fireEvent.click(scannerLink);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("console collapse and expansion preserve its content", () => {
  render(
    <AppShell>
      <Home />
    </AppShell>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Collapse console" }));
  expect(
    screen.queryByRole("region", { name: "System console content" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Expand console" }));
  expect(
    screen.getByRole("region", { name: "System console content" }),
  ).toHaveTextContent("Events and workflow history are not connected.");
});

test.each(Object.entries(stateLabels))(
  "state primitive %s has explicit text and appropriate semantics",
  (state, label) => {
    render(
      <SurfaceState
        state={state as keyof typeof stateLabels}
        title="Panel title"
        description="Panel description"
      />,
    );
    const surface = screen.getByRole(state === "ERROR" ? "alert" : "status");
    expect(surface).toHaveTextContent(label);
    expect(surface).toHaveTextContent("Panel description");
    expect(
      within(surface).getByRole("heading", { level: 3, name: "Panel title" }),
    ).toBeInTheDocument();
    expect(surface).toHaveAttribute("aria-busy", String(state === "LOADING"));
  },
);

test.each([
  ["loading", <Loading key="loading" />, [1]],
  [
    "error",
    <ErrorView key="error" error={new Error("test")} reset={() => {}} />,
    [1, 2],
  ],
  ["not-found", <NotFound key="not-found" />, [1, 2]],
] as const)(
  "%s view has a logical heading hierarchy",
  (_name, view, levels) => {
    render(view);
    expect(
      screen
        .getAllByRole("heading")
        .map((heading) => Number(heading.tagName.slice(1))),
    ).toEqual(levels);
  },
);

test("error recovery invokes reset without exposing error internals", () => {
  const reset = vi.fn();
  render(
    <ErrorView error={new Error("internal sensitive detail")} reset={reset} />,
  );
  expect(
    screen.queryByText("internal sensitive detail"),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(reset).toHaveBeenCalledOnce();
});

test("missing views offer a home link", () => {
  render(<NotFound />);
  expect(
    screen.getByRole("link", { name: "Back to workspace" }),
  ).toHaveAttribute("href", "/");
});
