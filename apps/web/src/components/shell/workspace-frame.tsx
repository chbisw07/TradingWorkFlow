import type { ReactNode } from "react";
import { ContextPanel } from "./context-panel";
import { ConsoleRegion } from "./console-region";
export function WorkspaceFrame({
  children,
  focused,
}: {
  children: ReactNode;
  focused: boolean;
}) {
  return (
    <div className="workspace-frame">
      <div className="workspace-grid">
        <main id="workspace" className="main-workspace" tabIndex={-1}>
          {children}
        </main>
        {!focused && <ContextPanel />}
      </div>
      {!focused && <ConsoleRegion />}
    </div>
  );
}
