"use client";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { TopBar } from "./top-bar";
import { PrimaryNavigation } from "./primary-navigation";
import { ContextPanel } from "./context-panel";
import { ConsoleRegion } from "./console-region";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const broker = pathname.startsWith("/brokers");
  const discovery =
    pathname.startsWith("/scanners") || pathname.startsWith("/candidates");
  const focused = broker || discovery;
  return (
    <div className={`app-shell${focused ? " focused-shell" : ""}`}>
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <TopBar focused={focused} />
      <div className="shell-grid">
        <PrimaryNavigation />
        <div className="workspace-frame">
          <div className="workspace-grid">
            <main id="workspace" className="main-workspace" tabIndex={-1}>
              {children}
            </main>
            {!focused && <ContextPanel />}
          </div>
          {!focused && <ConsoleRegion />}
        </div>
      </div>
      <footer className="status-bar">
        <p role="status">
          <span className="status-indicator" aria-hidden="true" />
          {broker
            ? "Broker workspace · Account-specific trading permissions"
            : discovery
              ? "Scan & Discover · Evidence, context and candidate history"
              : "Development shell · No live data"}
        </p>
        <span>
          {focused ? "TradingWorkFlow" : "TWF-1 Application Foundation"}
        </span>
      </footer>
    </div>
  );
}
