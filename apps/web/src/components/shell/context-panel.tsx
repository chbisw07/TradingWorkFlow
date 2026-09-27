"use client";

import { usePathname } from "next/navigation";
import { useRef } from "react";
import { Panel } from "../ui/panel";
import { SurfaceState } from "../ui/surface-state";
import { ServiceStatus } from "./service-status";

export function ContextPanel() {
  const pathname = usePathname();
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  if (pathname.startsWith("/brokers"))
    return (
      <aside className="broker-inspector" aria-label="Workspace details">
        <button
          ref={trigger}
          className="quiet-button"
          aria-haspopup="dialog"
          onClick={() => dialog.current?.showModal()}
        >
          Workspace details
        </button>
        <dialog
          ref={dialog}
          aria-labelledby="inspector-title"
          onClose={() => trigger.current?.focus()}
        >
          <div className="broker-room-heading">
            <h2 id="inspector-title">Workspace details</h2>
            <button
              className="quiet-button"
              onClick={() => dialog.current?.close()}
            >
              Close details
            </button>
          </div>
          <p className="panel-intro">
            Instrument and data details are available alongside each table.
            Service status can be checked here when troubleshooting.
          </p>
          <ServiceStatus />
        </dialog>
      </aside>
    );
  return (
    <aside className="context-panel" aria-label="Workspace context">
      <Panel id="services" title="Service connections">
        <ServiceStatus />
      </Panel>
      <Panel id="context" title="Instrument details">
        <SurfaceState
          state="EMPTY"
          title="No instrument selected"
          description="Instrument and workflow context will appear here when discovery is available."
        />
        <div className="context-footnote">
          Context stays with your workspace.
        </div>
      </Panel>
    </aside>
  );
}
