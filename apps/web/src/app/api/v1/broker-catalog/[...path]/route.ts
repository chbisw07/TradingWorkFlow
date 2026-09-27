import { apiOrigin } from "../../../../../lib/auth-server";
export const dynamic = "force-dynamic";

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const uuid =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const url = new URL(request.url);
  const allowedKeys = new Set([
    "text",
    "exchange",
    "segment",
    "instrument_type",
    "expiry",
    "strike",
    "derivative_kind",
    "name",
    "symbol",
    "version",
    "limit",
    "offset",
  ]);
  const output = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
  };
  if (
    path.length !== 3 ||
    path[0] !== "accounts" ||
    !uuid.test(path[1]) ||
    !(
      (request.method === "GET" && path[2] === "instruments") ||
      (request.method === "POST" && path[2] === "refresh")
    )
  )
    return Response.json(
      { error: { message: "Not found" } },
      { status: 404, headers: output },
    );
  if (
    url.search.length > 2048 ||
    [...url.searchParams.keys()].some(
      (key) =>
        !allowedKeys.has(key) || url.searchParams.getAll(key).length !== 1,
    ) ||
    (request.method === "POST" && url.search)
  )
    return Response.json(
      { error: { message: "Invalid catalog query" } },
      { status: 422, headers: output },
    );
  const headers = new Headers();
  const pairs = (request.headers.get("cookie") || "")
    .split(";")
    .map((pair) => pair.trim());
  for (const name of ["__Host-twf_session", "twf_session"]) {
    const matches = pairs.filter((pair) => pair.startsWith(name + "="));
    if (!matches.length) continue;
    if (
      matches.length === 1 &&
      /^[A-Za-z0-9_-]{43}$/.test(matches[0].slice(name.length + 1))
    )
      headers.set("Cookie", matches[0]);
    break;
  }
  const origin = request.headers.get("origin");
  if (origin) headers.set("Origin", origin);
  try {
    const response = await fetch(
      `${apiOrigin()}/api/v1/broker-catalog/${path.join("/")}${url.search}`,
      {
        method: request.method,
        headers,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(45000),
      },
    );
    return new Response(await response.text(), {
      status: response.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { error: { message: "Catalog unavailable. Try again." } },
      { status: 503, headers: output },
    );
  }
}
export const GET = forward;
export const POST = forward;
