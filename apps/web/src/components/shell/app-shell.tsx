"use client";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { TopBar } from "./top-bar";
import { PrimaryNavigation } from "./primary-navigation";
import { ContextPanel } from "./context-panel";
import { ConsoleRegion } from "./console-region";

export function AppShell({ children }: { children: ReactNode }) {
  const broker = usePathname().startsWith("/brokers");
  return (
    <div className={`app-shell${broker ? " broker-shell" : ""}`}>
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <TopBar broker={broker} />
      <div className="shell-grid">
        <PrimaryNavigation />
        <div className="workspace-frame">
          <div className="workspace-grid">
            <main id="workspace" className="main-workspace" tabIndex={-1}>
              {children}
            </main>
            {!broker && <ContextPanel />}
          </div>
          {!broker && <ConsoleRegion />}
        </div>
      </div>
      <footer className="status-bar">
        <p role="status">
          <span className="status-indicator" aria-hidden="true" />
          {broker
            ? "Broker workspace · Read only · Trading disabled"
            : "Development shell · No live data"}
        </p>
        <span>
          {broker ? "TradingWorkFlow" : "TWF-1 Application Foundation"}
        </span>
      </footer>
    </div>
  );
}
