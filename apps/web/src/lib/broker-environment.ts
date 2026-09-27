/** Evaluated on the server; no public client flag. This gates fixture discovery, not route authorization. */
export function brokerDevToolsEnabled(
  environment: string | undefined,
  nodeEnvironment: string | undefined,
) {
  if (environment === "production") return false;
  return (
    environment === "test" ||
    environment === "development" ||
    (!environment && nodeEnvironment === "development")
  );
}
