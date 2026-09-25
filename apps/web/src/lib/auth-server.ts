import { cookies } from "next/headers";
import type { CurrentUser } from "./current-user";

export function apiOrigin(): string {
  const value = process.env.TWF_API_ORIGIN || "http://127.0.0.1:8000";
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error("Invalid server API origin");
  }
  return url.origin;
}

export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const jar = await cookies();
  const session = jar.get("__Host-twf_session") || jar.get("twf_session");
  if (!session) return null;
  const response = await fetch(`${apiOrigin()}/api/v1/auth/me`, {
    headers: { Cookie: `${session.name}=${session.value}` },
    cache: "no-store",
    signal: AbortSignal.timeout(5000),
  });
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Unable to verify session");
  return response.json() as Promise<CurrentUser>;
}
