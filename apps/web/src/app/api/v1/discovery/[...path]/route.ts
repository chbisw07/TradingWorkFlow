import { apiOrigin } from "../../../../../lib/auth-server";

export const dynamic = "force-dynamic";

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const route = path.join("/");
  const id = "[0-9a-fA-F-]{36}";
  const allowed =
    request.method === "GET"
      ? /^(status|settings|scans|candidates|market-context)$/.test(route) ||
        new RegExp(`^scans/${id}$`).test(route) ||
        new RegExp(`^candidates/${id}$`).test(route)
      : request.method === "PUT"
        ? route === "settings"
        : request.method === "POST" &&
          (route === "scans" ||
            new RegExp(`^scans/${id}/(archive|restore)$`).test(route) ||
            new RegExp(`^candidates/${id}/(lifecycle|explain)$`).test(route));
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
    if (body && body.length > 16_384) {
      return new Response(null, { status: 413, headers: output });
    }
    const search = new URL(request.url).search;
    if (search.length > 1024) {
      return new Response(null, { status: 414, headers: output });
    }
    const upstream = await fetch(
      apiOrigin() + "/api/v1/discovery/" + route + search,
      {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(route === "scans" ? 65_000 : 15_000),
      },
    );
    const responseHeaders = { ...output } as Record<string, string>;
    const requestId = upstream.headers.get("X-Request-ID");
    if (requestId) responseHeaders["X-Request-ID"] = requestId;
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { error: { message: "Scan & Discover service is unavailable." } },
      { status: 503, headers: output },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
