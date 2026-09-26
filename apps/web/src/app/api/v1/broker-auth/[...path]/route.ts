import { apiOrigin } from "../../../../../lib/auth-server";
export const dynamic = "force-dynamic";

async function forward(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const route = path.join("/");
  const uuid =
    "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
  const allowed =
    (request.method === "GET" && route === "accounts") ||
    (request.method === "POST" &&
      (["finalize", "create-account"].includes(route) ||
        new RegExp(
          `^accounts/${uuid}/(configure|connect|disconnect|cleanup)$`,
        ).test(route)));
  const output = new Headers({
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  });
  if (!allowed)
    return Response.json(
      { error: { message: "Not found" } },
      { status: 404, headers: output },
    );
  const headers = new Headers({ "Content-Type": "application/json" });
  const pairs = (request.headers.get("cookie") || "")
    .split(";")
    .map((x) => x.trim());
  const cookies: string[] = [];
  for (const names of [
    ["__Host-twf_session", "twf_session"],
    ["__Host-twf_broker_finalize", "twf_broker_finalize"],
  ]) {
    for (const name of names) {
      const matches = pairs.filter((x) => x.startsWith(name + "="));
      if (!matches.length) continue;
      if (
        matches.length === 1 &&
        /^[A-Za-z0-9_-]{43}$/.test(matches[0].slice(name.length + 1))
      )
        cookies.push(matches[0]);
      break;
    }
  }
  if (cookies.length) headers.set("Cookie", cookies.join("; "));
  const origin = request.headers.get("origin");
  if (origin) headers.set("Origin", origin);
  try {
    let body: string | undefined;
    if (request.method === "POST") {
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 8192) {
            await reader.cancel();
            return new Response(null, { status: 413, headers: output });
          }
          chunks.push(value);
        }
      }
      body = new TextDecoder().decode(Buffer.concat(chunks));
    }
    const endpoint =
      route === "create-account"
        ? "/api/v1/broker-accounts"
        : "/api/v1/broker-auth/" + route;
    const upstream = await fetch(apiOrigin() + endpoint, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(15000),
    });
    for (const cookie of upstream.headers.getSetCookie()) {
      if (/^(?:__Host-)?twf_broker_finalize=/.test(cookie))
        output.append("Set-Cookie", cookie);
    }
    output.set("Content-Type", "application/json");
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { error: { message: "Broker authentication unavailable. Try again." } },
      { status: 503, headers: output },
    );
  }
}
export const GET = forward;
export const POST = forward;
