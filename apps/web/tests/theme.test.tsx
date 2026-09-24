import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ThemeToggle } from "../src/components/shell/theme-toggle";
import { themeInitializationScript, themeStorageKey } from "../src/lib/theme";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

test("defaults dark and exposes an accessible toggle that persists both choices", () => {
  window.eval(themeInitializationScript);
  render(<ThemeToggle />);
  const toggle = screen.getByRole("button", { name: "Light theme" });
  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  expect(toggle).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(toggle);
  expect(document.documentElement).toHaveAttribute("data-theme", "light");
  expect(toggle).toHaveAttribute("aria-pressed", "true");
  expect(localStorage.getItem(themeStorageKey)).toBe("light");
  fireEvent.click(toggle);
  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  expect(localStorage.getItem(themeStorageKey)).toBe("dark");
});

test.each([
  ["light", "light"],
  ["dark", "dark"],
  ["invalid", "dark"],
])("restores %s as %s before render", (saved, expected) => {
  localStorage.setItem(themeStorageKey, saved);
  window.eval(themeInitializationScript);
  render(<ThemeToggle />);
  expect(document.documentElement).toHaveAttribute("data-theme", expected);
  expect(screen.getByRole("button", { name: "Light theme" })).toHaveAttribute(
    "aria-pressed",
    String(expected === "light"),
  );
});

test("blocked storage keeps dark initialization and allows in-page switching", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(() => window.eval(themeInitializationScript)).not.toThrow();
  render(<ThemeToggle />);
  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  fireEvent.click(screen.getByRole("button", { name: "Light theme" }));
  expect(document.documentElement).toHaveAttribute("data-theme", "light");
});
