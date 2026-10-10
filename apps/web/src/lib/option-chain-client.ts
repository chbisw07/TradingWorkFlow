/** O2 is the sole source of chain identity, calculations and cache policy. */
export const chainMessages: Record<string, string> = {
  underlying_not_found: "This underlying has no listed option chain.",
  no_option_contracts:
    "No active option contracts are available for this selection.",
  expiry_not_found:
    "This expiry is no longer available. Select another expiry.",
  spot_unavailable:
    "Underlying spot is unavailable. ATM and moneyness are unavailable.",
  quote_unavailable:
    "Some quotes are unavailable. Listed contracts remain visible.",
  provider_unavailable:
    "Dhan market data unavailable. Check the connection in Settings.",
  partial_chain: "Partial chain. Some market values are unavailable.",
  unsupported_capability:
    "Some optional fields are not supported by this data source.",
};
export async function chainApi<T>(
  path: string,
  signal: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/v1/options/${path}`, {
    cache: "no-store",
    signal,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(
      response.status === 401
        ? "Your session has expired. Sign in again."
        : chainMessages[data?.error?.code] ||
            "Option chain could not be loaded. Check your selection and retry.",
    );
  }
  return data as T;
}
export const chainNumber = (
  value: string | number | null | undefined,
  maximumFractionDigits = 2,
) =>
  value == null || value === "" || !Number.isFinite(Number(value))
    ? "—"
    : Number(value).toLocaleString("en-IN", { maximumFractionDigits });
export const chainCompactNumber = (
  value: string | number | null | undefined,
  signed = false,
) => {
  if (value == null || value === "" || !Number.isFinite(Number(value)))
    return "—";
  const number = Number(value);
  const absolute = Math.abs(number);
  const unit = absolute >= 1_000_000 ? "M" : absolute >= 1_000 ? "K" : "";
  const scaled =
    unit === "M"
      ? absolute / 1_000_000
      : unit === "K"
        ? absolute / 1_000
        : absolute;
  const maximumFractionDigits =
    unit === "M"
      ? 2
      : unit === "K"
        ? scaled >= 100
          ? 0
          : scaled >= 10
            ? 1
            : 2
        : 2;
  const formatted = scaled.toLocaleString("en-IN", {
    maximumFractionDigits,
  });
  const prefix = number < 0 ? "−" : signed && number > 0 ? "+" : "";
  return `${prefix}${formatted}${unit}`;
};
export const expiryLabel = (value: string) =>
  new Date(`${value}T00:00:00Z`).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  });
export const retrievedLabel = (value: string) =>
  new Date(value).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "Asia/Kolkata",
  });
