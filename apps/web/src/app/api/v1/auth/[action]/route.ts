import { apiOrigin } from "../../../../../lib/auth-server";

export const dynamic = "force-dynamic";

function sessionCookie(header: string | null): string | undefined {
  const pairs = (header || "").split(";").map((part) => part.trim());
  // Match server identity resolution: prefer the production cookie if present.
  for (const name of ["__Host-twf_session", "twf_session"]) {
    const matches = pairs.filter((pair) => pair.startsWith(`${name}=`));
    if (!matches.length) continue;
    // Fail closed on duplicates; preserve valid cookie octets without decoding.
    if (matches.length !== 1) return undefined;
    const value = matches[0].slice(name.length + 1);
    return /^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]+$/.test(value)
      ? `${name}=${value}`
      : undefined;
  }
  return undefined;
}

async function forward(
  request: Request,
  context: { params: Promise<{ action: string }> },
) {
  const { action } = await context.params;
  if (!(
    (request.method === "GET" && action === "me") ||
    (request.method === "POST" && ["login", "logout"].includes(action))
  )) {
    return Response.json({ error: { message: "Not found" } }, { status: 404 });
  }
  const headers = new Headers();
  const cookie = sessionCookie(request.headers.get("cookie"));
  if (cookie) headers.set("Cookie", cookie);
  for (const name of ["origin", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const body = request.method === "POST" ? await request.text() : undefined;
    if (body && body.length > 4096) return new Response(null, { status: 413 });
    const upstream = await fetch(`${apiOrigin()}/api/v1/auth/${action}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
    });
    const output = new Headers({
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    });
    for (const cookie of upstream.headers.getSetCookie())
      output.append("Set-Cookie", cookie);
    for (const name of ["Retry-After", "X-Request-ID"]) {
      const value = upstream.headers.get(name);
      if (value !== null) output.set(name, value);
    }
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { error: { message: "Authentication service unavailable" } },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export const GET = forward;
export const POST = forward;
