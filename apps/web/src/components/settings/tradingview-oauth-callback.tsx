"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type CallbackState = "working" | "success" | "error";

export function TradingViewOAuthCallback() {
  const [state, setState] = useState<CallbackState>("working");
  const [message, setMessage] = useState(
    "Completing your owner-scoped TradingView authorization…",
  );
  const callbackStarted = useRef(false);

  useEffect(() => {
    if (callbackStarted.current) return;
    callbackStarted.current = true;
    const parameters = new URLSearchParams(window.location.search);
    const code = parameters.get("code") || "";
    const oauthState = parameters.get("state") || "";
    const connectionId = sessionStorage.getItem("twf.mcp.connection_id") || "";

    window.history.replaceState(null, "", "/settings/mcp/callback");

    if (
      !/^[0-9a-fA-F-]{36}$/.test(connectionId) ||
      !code ||
      code.length > 2048 ||
      !oauthState ||
      oauthState.length > 128
    ) {
      queueMicrotask(() => {
        setState("error");
        setMessage(
          "The authorization response is incomplete or no longer belongs to this browser session. Return to Settings and authorize again.",
        );
      });
      return;
    }

    fetch("/api/v1/settings/mcp/connections/" + connectionId + "/callback", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: oauthState, code }),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        await response.json();
        sessionStorage.removeItem("twf.mcp.connection_id");
        setState("success");
        setMessage(
          "TradingView authorization is saved. Return to Settings and test the provider connection before using real market evidence.",
        );
      })
      .catch(() => {
        setState("error");
        setMessage(
          "TradingView authorization could not be completed. Return to Settings and retry with a fresh authorization.",
        );
      });
  }, []);

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="mcp-callback-heading">
        <p className="eyebrow">TRADINGVIEW CONNECTION</p>
        <h1 id="mcp-callback-heading">
          {state === "working"
            ? "Completing authorization"
            : state === "success"
              ? "TradingView connected"
              : "Authorization incomplete"}
        </h1>
        <p role={state === "error" ? "alert" : "status"}>{message}</p>
        {state !== "working" && (
          <Link href="/settings">Return to Settings</Link>
        )}
      </section>
    </main>
  );
}
