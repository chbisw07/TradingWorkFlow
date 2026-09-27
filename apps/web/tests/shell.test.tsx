import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { AppShell } from "../src/components/shell/app-shell";
import { SurfaceState, stateLabels } from "../src/components/ui/surface-state";
import ErrorView from "../src/app/error";
import NotFound from "../src/app/not-found";
import Home from "../src/app/(protected)/page";
import Loading from "../src/app/loading";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

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
  expect(screen.getByRole("contentinfo")).toHaveTextContent("No live data");
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

test("only supported navigation is actionable and disclosure restores focus on Escape", () => {
  render(
    <AppShell>
      <Home />
    </AppShell>,
  );
  const nav = screen.getByRole("navigation", { name: "Primary navigation" });
  expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  for (const item of within(nav).getAllByRole("button", {
    name: /coming later/,
  }))
    expect(item).toBeDisabled();
  expect(
    within(nav).getAllByRole("button", { name: /coming later/ }),
  ).toHaveLength(8);
  const toggle = within(nav).getByRole("button", {
    name: "Workspace navigation",
  });
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  fireEvent.keyDown(nav, { key: "Escape" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(toggle).toHaveFocus();
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
