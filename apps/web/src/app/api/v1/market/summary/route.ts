import { apiOrigin } from "../../../../../lib/auth-server";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
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
    )
      headers.set("Cookie", matches[0]);
    break;
  }
  const output = {
    "Content-Type": "application/json",
    "Cache-Control": "private, no-store",
    "Referrer-Policy": "no-referrer",
  };
  try {
    const upstream = await fetch(`${apiOrigin()}/api/v1/market/summary`, {
      headers,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(15_000),
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return Response.json(
      { error: { message: "Market summary is temporarily unavailable." } },
      { status: 503, headers: output },
    );
  }
}
