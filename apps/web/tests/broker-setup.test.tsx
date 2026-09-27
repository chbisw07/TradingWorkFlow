import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import {
  BrokerSetupForm,
  type SetupInput,
} from "../src/components/brokers/broker-setup-form";
import {
  brokerProviders,
  type BrokerProviderManifest,
} from "../src/lib/broker-setup";
const fixture: BrokerProviderManifest = {
  ...brokerProviders[0],
  provider_id: "fixture-only",
  display_name: "Fixture Provider",
  auth_strategy: "SESSION_GENERATION",
  credential_fields: [
    {
      key: "client_id",
      label: "Client ID",
      kind: "CLIENT_ID",
      secret: false,
      required: true,
      lifecycle: "SESSION_ONLY",
      order: 1,
    },
    {
      key: "api_key",
      label: "API key",
      kind: "API_KEY",
      secret: false,
      required: true,
      lifecycle: "SESSION_ONLY",
      order: 2,
    },
    {
      key: "pin",
      label: "PIN",
      kind: "PIN",
      secret: true,
      required: true,
      lifecycle: "SESSION_ONLY",
      validation: { pattern: "[0-9]{4}", maxLength: 4 },
      order: 3,
    },
    {
      key: "totp",
      label: "TOTP",
      kind: "TOTP_CODE",
      secret: true,
      required: true,
      lifecycle: "ONE_TIME_INPUT",
      validation: { pattern: "[0-9]{6}", maxLength: 6 },
      order: 4,
    },
  ],
};
test("production manifest renders only the accepted credential fields", () => {
  render(<BrokerSetupForm manifest={brokerProviders[0]} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText("API key")).toHaveAttribute(
    "pattern",
    "[A-Za-z0-9_-]+",
  );
  expect(screen.getByLabelText("API secret")).toHaveAttribute(
    "type",
    "password",
  );
  for (const label of ["PIN", "Password", "TOTP", "Client ID"])
    expect(screen.queryByLabelText(label)).toBeNull();
  expect(
    brokerProviders.find((provider) => provider.provider_id === "fixture-only"),
  ).toBeUndefined();
});
test("one shared form renders a second strategy, clears all credentials before awaiting and retains none after failure", async () => {
  let reject!: (error: Error) => void;
  let submitted!: SetupInput;
  const handler = vi.fn((input: SetupInput) => {
    submitted = input;
    return new Promise<void>((_, failure) => {
      reject = failure;
    });
  });
  render(<BrokerSetupForm manifest={fixture} onSubmit={handler} />);
  fireEvent.change(screen.getByLabelText("Connection name"), {
    target: { value: "Fixture" },
  });
  for (const [label, value] of [
    ["Client ID", "client"],
    ["API key", "key"],
    ["PIN", "1234"],
    ["TOTP", "123456"],
  ])
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.submit(screen.getByRole("form"));
  expect(submitted.credentials).toEqual({
    client_id: "client",
    api_key: "key",
    pin: "1234",
    totp: "123456",
  });
  for (const label of ["Client ID", "API key", "PIN", "TOTP"])
    expect(screen.getByLabelText(label)).toHaveValue("");
  expect(screen.getByLabelText("PIN")).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("TOTP")).toHaveAttribute(
    "autocomplete",
    "one-time-code",
  );
  fireEvent.submit(screen.getByRole("form"));
  expect(handler).toHaveBeenCalledTimes(1);
  reject(new Error("secret-provider-error-123456"));
  await screen.findByRole("alert");
  expect(document.body.textContent).not.toContain("123456");
  expect(submitted.credentials).toEqual({});
  expect(localStorage.getItem("totp")).toBeNull();
});
test.each(["TOTP_CODE", "PIN", "PASSWORD", "TOTP_SECRET"] as const)(
  "unsupported persistent %s fails closed",
  (kind) => {
    render(
      <BrokerSetupForm
        manifest={{
          ...fixture,
          credential_fields: [
            {
              key: "unsafe",
              label: "Unsafe",
              kind,
              secret: true,
              required: true,
              lifecycle: "PERSISTENT_SECRET",
              order: 1,
            },
          ],
        }}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.queryByRole("form")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("not available");
  },
);
test("successful save never echoes secret values and removes transient submission credentials", async () => {
  let submitted!: SetupInput;
  render(
    <BrokerSetupForm
      manifest={brokerProviders[0]}
      onSubmit={async (input) => {
        submitted = input;
      }}
    />,
  );
  fireEvent.change(screen.getByLabelText("API secret"), {
    target: { value: "only-in-flight" },
  });
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(submitted.credentials).toEqual({}));
  expect(screen.getByLabelText("API secret")).toHaveValue("");
  expect(document.body.innerHTML).not.toContain("only-in-flight");
});
