/** Presentation metadata only. Backend policy and account permissions remain authoritative. */
export type CredentialKind =
  | "TEXT"
  | "CLIENT_ID"
  | "API_KEY"
  | "API_SECRET"
  | "TOKEN"
  | "TOTP_CODE"
  | "TOTP_SECRET"
  | "PIN"
  | "PASSWORD";
export type CredentialLifecycle =
  "ONE_TIME_INPUT" | "SESSION_ONLY" | "PERSISTENT_SECRET";
export type CredentialFieldDefinition = {
  key: string;
  label: string;
  kind: CredentialKind;
  required: boolean;
  secret: boolean;
  lifecycle: CredentialLifecycle;
  placeholder?: string;
  validation?: { minLength?: number; maxLength?: number; pattern?: string };
  order: number;
};
export type BrokerProviderManifest = {
  provider_id: string;
  display_name: string;
  support_state: "SUPPORTED" | "COMING_LATER";
  operational_room: "ZERODHA" | null;
  auth_strategy:
    | "BROWSER_REDIRECT_CALLBACK"
    | "DIRECT_CREDENTIALS"
    | "TOKEN_BASED"
    | "SESSION_GENERATION"
    | "MANUAL_TOKEN"
    | null;
  credential_fields: readonly CredentialFieldDefinition[];
  capabilities: Readonly<
    Record<
      | "profile"
      | "catalog"
      | "search"
      | "holdings"
      | "positions"
      | "orders"
      | "funds"
      | "streaming"
      | "commands",
      boolean
    >
  >;
};
const unavailable = {
  profile: false,
  catalog: false,
  search: false,
  holdings: false,
  positions: false,
  orders: false,
  funds: false,
  streaming: false,
  commands: false,
};
export const brokerProviders: readonly BrokerProviderManifest[] = [
  {
    provider_id: "zerodha",
    display_name: "Zerodha",
    support_state: "SUPPORTED",
    operational_room: "ZERODHA",
    auth_strategy: "BROWSER_REDIRECT_CALLBACK",
    credential_fields: [
      {
        key: "api_key",
        label: "API key",
        kind: "API_KEY",
        required: true,
        secret: false,
        lifecycle: "PERSISTENT_SECRET",
        validation: { maxLength: 128, pattern: "[A-Za-z0-9_-]+" },
        order: 1,
      },
      {
        key: "api_secret",
        label: "API secret",
        kind: "API_SECRET",
        required: true,
        secret: true,
        lifecycle: "PERSISTENT_SECRET",
        validation: { maxLength: 4096 },
        order: 2,
      },
    ],
    capabilities: {
      ...unavailable,
      profile: true,
      catalog: true,
      search: true,
      holdings: true,
      positions: true,
    },
  },
  ...[
    ["angelone", "Angel One"],
    ["fyers", "Fyers"],
    ["dhan", "Dhan"],
  ].map(([provider_id, display_name]): BrokerProviderManifest => ({
    provider_id,
    display_name,
    support_state: "COMING_LATER",
    operational_room: null,
    auth_strategy: null,
    credential_fields: [],
    capabilities: unavailable,
  })),
];
export function providerName(id: string) {
  return (
    brokerProviders.find((provider) => provider.provider_id === id)
      ?.display_name || "Broker"
  );
}
export function isSecretField(field: CredentialFieldDefinition) {
  return (
    field.secret ||
    [
      "API_SECRET",
      "TOKEN",
      "TOTP_CODE",
      "TOTP_SECRET",
      "PIN",
      "PASSWORD",
    ].includes(field.kind)
  );
}
/** Invalid lifecycle declarations fail closed. Persistence requires an implemented backend strategy. */
export function validCredentialManifest(manifest: BrokerProviderManifest) {
  const keys = new Set<string>();
  return (
    manifest.support_state === "SUPPORTED" &&
    manifest.auth_strategy !== null &&
    manifest.credential_fields.every((field) => {
      if (
        !/^[a-z][a-z0-9_]*$/.test(field.key) ||
        field.key === "label" ||
        keys.has(field.key)
      )
        return false;
      keys.add(field.key);
      if (field.kind === "TOTP_CODE" && field.lifecycle !== "ONE_TIME_INPUT")
        return false;
      // No currently supported strategy requires persistent PINs/passwords/TOTP seeds.
      if (
        ["PIN", "PASSWORD", "TOTP_SECRET"].includes(field.kind) &&
        field.lifecycle === "PERSISTENT_SECRET"
      )
        return false;
      return true;
    })
  );
}
