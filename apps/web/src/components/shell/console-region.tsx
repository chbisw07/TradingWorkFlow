"use client";

import { useState } from "react";
import { StateBadge } from "../ui/surface-state";

export function ConsoleRegion() {
  const [expanded, setExpanded] = useState(true);
  return (
    <section className="console-region panel" aria-labelledby="console-title">
      <div className="console-heading">
        <h2 id="console-title">
          <span aria-hidden="true">›_</span> System console
        </h2>
        <StateBadge state="DISCONNECTED" label="No live stream" />
        <button
          className="quiet-button"
          type="button"
          aria-expanded={expanded}
          aria-controls="console-content"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Collapse console" : "Expand console"}
          <span aria-hidden="true">{expanded ? "−" : "+"}</span>
        </button>
      </div>
      <div
        id="console-content"
        className="console-content"
        hidden={!expanded}
        tabIndex={0}
        role="region"
        aria-label="System console content"
      >
        <span className="console-prefix">NOTE</span>
        <p>Development shell. Events and workflow history are not connected.</p>
      </div>
    </section>
  );
}
