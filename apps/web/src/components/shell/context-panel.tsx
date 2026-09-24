import { Panel } from "../ui/panel";
import { StateBadge, SurfaceState } from "../ui/surface-state";

export const developmentServices = [
  ["TWF API", "Not checked"],
  ["Scanner", "Not connected"],
  ["TI", "Not connected"],
  ["TM", "Not connected"],
  ["LLM", "Not configured"],
  ["Broker", "Not connected"],
] as const;

export function ContextPanel() {
  return (
    <aside className="context-panel" aria-label="Workspace context">
      <Panel
        id="services"
        title="Service connections"
        eyebrow="DEVELOPMENT"
        meta={<span className="panel-index">01 / 02</span>}
      >
        <p className="panel-intro">
          Static placeholders. No health checks are running.
        </p>
        <dl className="service-list">
          {developmentServices.map(([name, label]) => (
            <div key={name}>
              <dt>
                <span className="service-monogram" aria-hidden="true">
                  {name === "TWF API" ? "API" : name.slice(0, 2).toUpperCase()}
                </span>
                <span>{name}</span>
              </dt>
              <dd>
                <StateBadge
                  state={
                    label === "Not configured" ? "UNAVAILABLE" : "DISCONNECTED"
                  }
                  label={label}
                />
              </dd>
            </div>
          ))}
        </dl>
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
