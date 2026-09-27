import { Panel } from "../ui/panel";
import { SurfaceState } from "../ui/surface-state";

import { ServiceStatus } from "./service-status";

export function ContextPanel() {
  return (
    <aside className="context-panel" aria-label="Workspace context">
      <Panel
        id="services"
        title="Service connections"
        eyebrow="FOUNDATION"
        meta={<span className="panel-index">01 / 02</span>}
      >
        <ServiceStatus />
      </Panel>
      <Panel
        id="context"
        title="Selected context"
        eyebrow="WORKSPACE"
        meta={<span className="panel-index">02 / 02</span>}
      >
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
