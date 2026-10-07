import { apiOrigin } from "../../../../../lib/auth-server";

export const dynamic = "force-dynamic";

async function forward(
  request: Request,
  context: { params: Promise<{ path?: string[] }> },
) {
  const { path } = await context.params;
  const route = (path || []).join("/");
  const id = "[0-9a-fA-F-]{36}";
  const allowed =
    request.method === "GET"
      ? route === "" ||
        route === "instruments" ||
        new RegExp(
          `^${id}(/(export|universe|quotes)|/items/${id}/(chart|news|reference|broker-instrument))?$`,
        ).test(route)
      : request.method === "PATCH"
        ? new RegExp(`^${id}$`).test(route)
        : request.method === "DELETE"
          ? new RegExp(`^${id}/items/${id}$`).test(route)
          : request.method === "POST" &&
            (route === "" ||
              route === "trash/restore" ||
              route === "trash/permanent-delete" ||
              new RegExp(`^${id}/(items|remove|transfer|notes|import)$`).test(
                route,
              ));
  const output = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  };
  if (!allowed) {
    return Response.json(
      { error: { message: "Not found" } },
      { status: 404, headers: output },
    );
  }
  const headers = new Headers();
  const pairs = (request.headers.get("cookie") || "")
    .split(";")
    .map((value) => value.trim());
  for (const name of ["__Host-twf_session", "twf_session"]) {
    const matches = pairs.filter((value) => value.startsWith(name + "="));
    if (!matches.length) continue;
    if (
      matches.length === 1 &&
      /^[A-Za-z0-9_-]{3,128}$/.test(matches[0].slice(name.length + 1))
    ) {
      headers.set("Cookie", matches[0]);
    }
    break;
  }
  for (const name of ["origin", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const body = request.method === "GET" ? undefined : await request.text();
    if (body && body.length > 40_000) {
      return new Response(null, { status: 413, headers: output });
    }
    const search = new URL(request.url).search;
    if (search.length > 1024) {
      return new Response(null, { status: 414, headers: output });
    }
    const upstream = await fetch(
      apiOrigin() + "/api/v1/watchlists" + (route ? "/" + route : "") + search,
      {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(
          route.endsWith("/news") || route.endsWith("/reference")
            ? 30_000
            : 15_000,
        ),
      },
    );
    const responseHeaders = { ...output } as Record<string, string>;
    if (route.endsWith("/export") && upstream.ok) {
      responseHeaders["Content-Type"] = "text/csv";
      responseHeaders["Content-Disposition"] =
        'attachment; filename="watchlist.csv"';
    }
    const requestId = upstream.headers.get("X-Request-ID");
    if (requestId) responseHeaders["X-Request-ID"] = requestId;
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { error: { message: "Watchlists service is unavailable." } },
      { status: 503, headers: output },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
