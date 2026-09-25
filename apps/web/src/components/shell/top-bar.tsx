import Link from "next/link";
import { UserMenu } from "../auth/user-session";
import { StateBadge } from "../ui/surface-state";
import { ThemeToggle } from "./theme-toggle";

export function TopBar() {
  return (
    <header className="top-bar">
      <div className="top-bar-primary">
        <Link href="/" className="brand" aria-label="TradingWorkFlow home">
          <span className="brand-mark" aria-hidden="true">
            twf<span>.</span>
          </span>
          <span className="brand-name">TradingWorkFlow</span>
        </Link>
        <span className="workspace-name">
          <span className="muted">Workspace</span> Default
        </span>
        <div className="top-bar-user">
          <ThemeToggle />
          <StateBadge state="COMING_SOON" label="Development" />
          <UserMenu />
        </div>
      </div>
      <dl className="session-strip" aria-label="Session context">
        <div>
          <dt>Broker</dt>
          <dd>Not connected</dd>
        </div>
        <div>
          <dt>Market / session</dt>
          <dd>Not selected</dd>
        </div>
        <div>
          <dt>Active LLM</dt>
          <dd>Not configured</dd>
        </div>
        <div>
          <dt>Alerts</dt>
          <dd>Not enabled</dd>
        </div>
        <div className="session-services">
          <dt>Services</dt>
          <dd>Development placeholders</dd>
        </div>
      </dl>
    </header>
  );
}
