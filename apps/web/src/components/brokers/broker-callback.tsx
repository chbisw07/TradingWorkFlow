"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { brokerApi, type Account } from "../../lib/brokers";
export function BrokerCallback() {
  const started = useRef(false);
  const [message, setMessage] = useState("Verifying your broker account…");
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const params = new URLSearchParams(window.location.search);
    window.history.replaceState(null, "", "/brokers/callback");
    const state = params.get("state");
    if (
      !state ||
      params.getAll("state").length !== 1 ||
      params.getAll("request_token").length > 1 ||
      params.getAll("status").length > 1
    ) {
      queueMicrotask(() =>
        setMessage(
          "Invalid broker callback. Return to Manage Brokers and reconnect.",
        ),
      );
      return;
    }
    void brokerApi<Account>("callback", {
      state,
      request_token:
        params.get("status") === null || params.get("status") === "success"
          ? params.get("request_token")
          : null,
    })
      .then((account) => {
        try {
          localStorage.setItem("twf-broker-change", account.updated_at);
        } catch {
          /* optional cross-tab notification */
        }
        window.location.replace(`/brokers/accounts/${account.id}/overview`);
      })
      .catch((error: Error) => setMessage(error.message));
  }, []);
  return (
    <main className="broker-callback">
      <h1>Connect broker</h1>
      <p role="status">{message}</p>
      <Link className="broker-button" href="/brokers/manage/my">
        Back to My Brokers
      </Link>
    </main>
  );
}
