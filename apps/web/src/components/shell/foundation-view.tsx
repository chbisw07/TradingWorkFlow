import { Panel } from "../ui/panel";
import { StateBadge, SurfaceState } from "../ui/surface-state";

export function FoundationView() {
  return (
    <>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">DEFAULT WORKSPACE / HOME</p>
          <h1>
            Workspace overview
            <span className="heading-dot" aria-hidden="true">
              .
            </span>
          </h1>
        </div>
        <StateBadge state="READY" label="Shell preview" />
      </div>
      <Panel
        id="workspace-foundation"
        title="Your workspace starts here"
        eyebrow="APPLICATION FOUNDATION"
        meta={<span className="panel-index">TWF / 1.1</span>}
        className="foundation-panel"
      >
        <div className="foundation-message">
          <div className="foundation-symbol" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div>
            <h3>A clear view. A connected workflow.</h3>
            <p>
              The foundation for your trading day is taking shape. This preview
              establishes the workspace; trading tools and service connections
              come next.
            </p>
          </div>
        </div>
        <dl className="foundation-facts">
          <div>
            <dt>Current target</dt>
            <dd>TWF-1.1 Frontend Shell</dd>
          </div>
          <div>
            <dt>Architecture</dt>
            <dd>
              <span className="accepted-mark" aria-hidden="true">
                ✓
              </span>{" "}
              TWF-0 Accepted
            </dd>
          </div>
          <div>
            <dt>Next target</dt>
            <dd>TWF-1.2 Backend Shell</dd>
          </div>
        </dl>
        <div className="foundation-note">
          <span className="mono">PREVIEW</span>
          <span>Workspace layout only. No market data or trading actions.</span>
        </div>
      </Panel>
      <Panel
        id="activity"
        title="Workspace activity"
        eyebrow="WORKFLOW"
        meta={<StateBadge state="COMING_SOON" />}
        className="activity-panel"
      >
        <SurfaceState
          state="EMPTY"
          title="A quiet workspace, by design"
          description="Candidates, positions and workflow activity will appear as the application foundation develops."
        />
      </Panel>
      <div className="workspace-boundary">
        <span className="boundary-line" />
        <p>Analysis, trading authority and execution remain distinct.</p>
        <span className="boundary-line" />
      </div>
    </>
  );
}
