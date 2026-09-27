"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { brokerAuthRequest } from "./real-brokers";

export function BrokerAuthComplete() {
  const started = useRef(false);
  const [state, setState] = useState("Verifying your account…");
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    brokerAuthRequest("finalize", {})
      .then(() => setState("Zerodha connected. Provider account verified."))
      .catch(() =>
        setState(
          "Connection could not be verified. Sign in with the original TWF session, then retry Connect from Brokers.",
        ),
      );
  }, []);
  return (
    <main className="broker-callback">
      <h1>Zerodha connection</h1>
      <p role="status">{state}</p>
      <p className="broker-mode">LIVE DATA · READ ONLY</p>
      <p className="broker-safety-label">TRADING DISABLED</p>
      <p>
        Open your broker room for holdings, positions and instruments. Orders
        and funds are deferred.
      </p>
      <Link href="/brokers">Return to Brokers</Link>
    </main>
  );
}
