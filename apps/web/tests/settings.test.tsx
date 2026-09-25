import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SettingsCenter } from "../src/components/settings/settings-center";
const initial = {
  revision: 0,
  overrides: {},
  effective: { density: "comfortable", default_horizon: "5d" },
  sources: { density: "PLATFORM", default_horizon: "PLATFORM" },
  active_profile_id: null,
  applied_profile_revision: null,
};
function response(data: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => data };
}
afterEach(() => vi.unstubAllGlobals());
test("loading and empty profiles, save, reset and device-local theme explanation", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(response(initial))
    .mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(
      response({
        ...initial,
        revision: 1,
        overrides: { density: "compact" },
        effective: { ...initial.effective, density: "compact" },
        sources: { ...initial.sources, density: "USER" },
      }),
    )
    .mockResolvedValueOnce(response({ ...initial, revision: 2 }));
  vi.stubGlobal("fetch", fetcher);
  render(<SettingsCenter />);
  expect(screen.getByText("Loading preferences")).toBeInTheDocument();
  await screen.findByText(/No profiles yet/);
  expect(
    screen.getByText(/Theme is a device-local preference/),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Setup density"), {
    target: { value: "compact" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save and apply preferences" }),
  );
  await screen.findByText("Preferences saved and applied.");
  expect(JSON.parse(fetcher.mock.calls[2][1].body)).toEqual({
    revision: 0,
    values: { density: "compact" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Reset preferences to defaults" }),
  );
  await screen.findByText("Defaults restored.");
  expect(screen.getByLabelText("Setup density")).toHaveValue("");
});
test.each([401, 403, 409, 422, 503])(
  "mutation failure %s is explicit without fake success",
  async (status) => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response(initial))
        .mockResolvedValueOnce(response([]))
        .mockResolvedValueOnce(response({}, status)),
    );
    render(<SettingsCenter />);
    await screen.findByLabelText("Setup density");
    fireEvent.click(
      screen.getByRole("button", { name: "Save and apply preferences" }),
    );
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(
      screen.queryByText("Preferences saved and applied."),
    ).not.toBeInTheDocument();
  },
);
test("load failure offers retry and profile save requires explicit application", async () => {
  const profile = { id: "one", name: "Desk", revision: 1, values: {} };
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(response({}, 503))
    .mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(response(initial))
    .mockResolvedValueOnce(response([]))
    .mockResolvedValueOnce(response(profile));
  vi.stubGlobal("fetch", fetcher);
  render(<SettingsCenter />);
  await screen.findByRole("alert");
  fireEvent.click(
    screen.getByRole("button", { name: "Reload current values" }),
  );
  await screen.findByLabelText("Profile name");
  fireEvent.change(screen.getByLabelText("Profile name"), {
    target: { value: "Desk" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create profile" }));
  await screen.findByRole("button", { name: "Apply Desk" });
  await waitFor(() =>
    expect(screen.getByText(/Profile saved and validated/)).toBeInTheDocument(),
  );
  expect(
    fetcher.mock.calls.filter((c) => String(c[0]).endsWith("/apply")),
  ).toHaveLength(0);
});
