import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import {
  DerivativeTemplateMenu,
  type DerivativeTemplate,
} from "../src/components/scanner/derivative-template-menu";
import { DerivativeSaveMenu } from "../src/components/scanner/derivative-save-menu";

const base: DerivativeTemplate = {
  template_id: "builtin:liquid",
  name: "Intraday — Liquid ATM Options",
  scanner_type: "DERIVATIVES",
  instrument_scope: "OPTIONS",
  horizon: "INTRADAY",
  source: "BUILT_IN",
  description: "Liquid ATM options",
  template_schema_version: 1,
  recipe: {
    scanner_type: "DERIVATIVES",
    instrument_scope: "OPTIONS",
    expiry_mode: "NEAREST",
    exact_expiry: null,
    strike_window: 10,
    watchlist_id: null,
    predicates: [{ field: "volume_percentile", operator: ">=", value: 70 }],
  },
};

test("grouped templates load explicitly and Escape restores focus", () => {
  const onLoad = vi.fn();
  const positional: DerivativeTemplate = {
    ...base,
    template_id: "builtin:positional",
    name: "Positional — Bullish Call Setup",
    horizon: "POSITIONAL",
  };
  const mine: DerivativeTemplate = {
    ...base,
    template_id: "11111111-1111-4111-8111-111111111111",
    name: "My Calls",
    horizon: "GENERAL",
    source: "USER",
  };
  render(
    <DerivativeTemplateMenu
      builtIn={[base, positional]}
      user={[mine]}
      onLoad={onLoad}
      onRename={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
  const trigger = screen.getByRole("button", { name: /Scan Templates/ });
  fireEvent.click(trigger);
  const menu = screen.getByRole("menu", { name: "Scan Templates" });
  expect(within(menu).getByRole("region", { name: "Intraday" })).toBeVisible();
  expect(
    within(menu).getByRole("region", { name: "Positional" }),
  ).toBeVisible();
  expect(
    within(menu).getByRole("region", { name: "My Templates" }),
  ).toBeVisible();
  expect(within(menu).getAllByRole("button", { name: /Rename/ })).toHaveLength(
    1,
  );
  expect(within(menu).getAllByRole("button", { name: /Delete/ })).toHaveLength(
    1,
  );
  fireEvent.click(
    within(menu).getByRole("menuitem", { name: /Liquid ATM Options/ }),
  );
  expect(onLoad).toHaveBeenCalledWith(base);
  fireEvent.click(trigger);
  fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
  expect(
    screen.getByRole("menuitem", { name: /Positional — Bullish/ }),
  ).toHaveFocus();
  fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  expect(trigger).toHaveFocus();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
});

test("Save Scan chooser keeps scan and template actions distinct", () => {
  const onSaveScan = vi.fn(),
    onSaveTemplate = vi.fn();
  render(
    <DerivativeSaveMenu
      onSaveScan={onSaveScan}
      onSaveTemplate={onSaveTemplate}
    />,
  );
  const trigger = screen.getByRole("button", { name: /Save Scan/ });
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("menuitem", { name: /Save as Template/ }));
  expect(onSaveTemplate).toHaveBeenCalledOnce();
  expect(onSaveScan).not.toHaveBeenCalled();
  fireEvent.click(trigger);
  fireEvent.click(screen.getByRole("menuitem", { name: /^Save Scan/ }));
  expect(onSaveScan).toHaveBeenCalledOnce();
});
