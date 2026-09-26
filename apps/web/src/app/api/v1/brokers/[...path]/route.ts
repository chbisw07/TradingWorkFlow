import { apiOrigin } from "../../../../../lib/auth-server";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const allowed =
    (path.length === 1 && path[0] === "overview") ||
    (path.length === 2 &&
      path[0] === "accounts" &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        path[1],
      ));
  const supplied = request.headers.get("X-Request-ID") || "";
  const requestId = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(supplied)
    ? supplied
    : crypto.randomUUID();
  const headers = new Headers({ "X-Request-ID": requestId });
  const pairs = (request.headers.get("cookie") || "")
    .split(";")
    .map((part) => part.trim());
  for (const name of ["__Host-twf_session", "twf_session"]) {
    const matches = pairs.filter((pair) => pair.startsWith(`${name}=`));
    if (!matches.length) continue;
    const value = matches[0].slice(name.length + 1);
    if (
      matches.length === 1 &&
      /^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]+$/.test(value)
    )
      headers.set("Cookie", `${name}=${value}`);
    break;
  }
  const output = new Headers({
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "X-Request-ID": requestId,
  });
  if (!allowed)
    return Response.json(
      {
        error: {
          code: "HTTP_404",
          message: "Not Found",
          request_id: requestId,
          details: null,
        },
      },
      { status: 404, headers: output },
    );
  try {
    const response = await fetch(
      `${apiOrigin()}/api/v1/brokers/${path.join("/")}`,
      {
        headers,
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(12000),
      },
    );
    return new Response(await response.text(), {
      status: response.status,
      headers: output,
    });
  } catch {
    return Response.json(
      {
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: "Broker observations unavailable",
          request_id: requestId,
          details: null,
        },
      },
      { status: 503, headers: output },
    );
  }
}
