import { apiOrigin } from "../../../../../lib/auth-server";
export const dynamic = "force-dynamic";

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const route = path.join("/");
  const uuid = "[0-9a-fA-F-]{36}";
  const allowed =
    (request.method === "GET" &&
      ["definitions", "values", "profiles"].includes(route)) ||
    (request.method === "PUT" &&
      (route === "values" ||
        new RegExp("^profiles/" + uuid + "$").test(route))) ||
    (request.method === "POST" &&
      (["reset", "deactivate", "profiles"].includes(route) ||
        new RegExp("^profiles/" + uuid + "/apply$").test(route)));
  const output = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
  };
  if (!allowed)
    return Response.json(
      { error: { message: "Not found" } },
      { status: 404, headers: output },
    );
  const headers = new Headers();
  const pairs = (request.headers.get("cookie") || "")
    .split(";")
    .map((x) => x.trim());
  for (const name of ["__Host-twf_session", "twf_session"]) {
    const matches = pairs.filter((x) => x.startsWith(name + "="));
    if (!matches.length) continue;
    if (
      matches.length === 1 &&
      /^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]+$/.test(
        matches[0].slice(name.length + 1),
      )
    )
      headers.set("Cookie", matches[0]);
    break;
  }
  for (const name of ["origin", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const body = request.method === "GET" ? undefined : await request.text();
    if (body && body.length > 4096)
      return new Response(null, { status: 413, headers: output });
    const upstream = await fetch(apiOrigin() + "/api/v1/settings/" + route, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    });
    const responseHeaders = new Headers(output);
    const id = upstream.headers.get("X-Request-ID");
    if (id) responseHeaders.set("X-Request-ID", id);
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { error: { message: "Settings unavailable" } },
      { status: 503, headers: output },
    );
  }
}
export const GET = forward;
export const PUT = forward;
export const POST = forward;
