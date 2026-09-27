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
      ? /^(providers|accounts|setup)$/.test(route) ||
        new RegExp(
          `^accounts/${id}/(overview|holdings|positions|orders|funds|instruments)$`,
        ).test(route)
      : request.method === "POST" &&
        (/^(accounts|callback)$/.test(route) ||
          new RegExp(`^accounts/${id}/(connect|disconnect)$`).test(route));
  const output = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
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
      /^[A-Za-z0-9_-]{43}$/.test(matches[0].slice(name.length + 1))
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
    const search = new URL(request.url).search;
    if (search.length > 1024)
      return new Response(null, { status: 414, headers: output });
    const upstream = await fetch(
      apiOrigin() + "/api/v1/brokers/" + route + search,
      {
        method: request.method,
        headers,
        body,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(65000),
      },
    );
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { error: { message: "Broker service is unavailable. Please retry." } },
      { status: 503, headers: output },
    );
  }
}
export const GET = forward;
export const POST = forward;
