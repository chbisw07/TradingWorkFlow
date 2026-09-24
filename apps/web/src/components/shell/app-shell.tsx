import type { ReactNode } from "react";
import { TopBar } from "./top-bar";
import { PrimaryNavigation } from "./primary-navigation";
import { ContextPanel } from "./context-panel";
import { ConsoleRegion } from "./console-region";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <TopBar />
      <div className="shell-grid">
        <PrimaryNavigation />
        <div className="workspace-frame">
          <div className="workspace-grid">
            <main id="workspace" className="main-workspace" tabIndex={-1}>
              {children}
            </main>
            <ContextPanel />
          </div>
          <ConsoleRegion />
        </div>
      </div>
      <footer className="status-bar">
        <p role="status">
          <span className="status-indicator" aria-hidden="true" />
          Development shell · No live data
        </p>
        <span>TWF-1 Application Foundation</span>
      </footer>
    </div>
  );
}
