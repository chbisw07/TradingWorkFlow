import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { LoginForm } from "../src/components/auth/login-form";
import { UserMenu, UserSession } from "../src/components/auth/user-session";

const { replace, refresh } = vi.hoisted(() => ({
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh }) }));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

test("accessible login submits credentials and redirects", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", fetcher);
  render(<LoginForm />);
  fireEvent.change(screen.getByLabelText("Username"), {
    target: { value: "alice" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "test-only-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  expect(fetcher).toHaveBeenCalledWith(
    "/api/v1/auth/login",
    expect.objectContaining({ method: "POST" }),
  );
  expect(screen.getByLabelText("Password")).toHaveValue("");
});

test("invalid login has a generic accessible error and can retry", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401 }));
  render(<LoginForm />);
  fireEvent.submit(screen.getByLabelText("Password").closest("form")!);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Check your username and password",
  );
  expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
});

test("pending login exposes loading state", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {})),
  );
  render(<LoginForm />);
  fireEvent.submit(screen.getByLabelText("Password").closest("form")!);
  expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("Verifying");
});

const user = {
  id: "fixture-id",
  username: "alice",
  display_name: "Alice Trader",
};
test("current identity is displayed and logout returns to login", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
  render(
    <UserSession user={user}>
      <UserMenu />
    </UserSession>,
  );
  expect(screen.getByText("Alice Trader")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
});

test("expired session on window focus redirects to login", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 401 }));
  render(
    <UserSession user={user}>
      <UserMenu />
    </UserSession>,
  );
  fireEvent(window, new Event("focus"));
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
});

test("failed logout remains visible and offers retry", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
  render(
    <UserSession user={user}>
      <UserMenu />
    </UserSession>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to sign out",
  );
  expect(replace).not.toHaveBeenCalled();
});
