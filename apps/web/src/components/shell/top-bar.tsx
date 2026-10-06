import Link from "next/link";
import { UserMenu } from "../auth/user-session";
import { ThemeToggle } from "./theme-toggle";
import { Icon } from "./icon";
import { MarketTickerSummary } from "./market-ticker-summary";

export function TopBar({
  onOpenNavigation,
  navigationOpen,
}: {
  onOpenNavigation: () => void;
  navigationOpen: boolean;
}) {
  return (
    <header className="top-bar">
      <div className="top-bar-primary">
        <button
          type="button"
          className="shell-icon-button nav-toggle"
          aria-label="Workspace navigation"
          aria-expanded={navigationOpen}
          aria-controls="mobile-navigation"
          onClick={onOpenNavigation}
        >
          <Icon name="menu" />
        </button>
        <Link href="/" className="brand" aria-label="TradingWorkFlow home">
          <span className="brand-mark" aria-hidden="true">
            twf<span>.</span>
          </span>
          <span className="brand-copy">
            <span className="brand-name">TradingWorkFlow</span>
            <span className="brand-tagline">
              Scan. Discover. Trade Smarter.
            </span>
          </span>
        </Link>
        <div
          className="global-search"
          role="search"
          aria-label="Global symbol search"
        >
          <Icon name="search" />
          <input
            type="search"
            disabled
            aria-label="Search symbol — coming later"
            placeholder="Search symbol (e.g. RELIANCE, NIFTY, BANKNIFTY...)"
          />
          <span>Coming later</span>
        </div>
        <MarketTickerSummary />
        <div className="top-bar-user">
          <button
            className="shell-icon-button notifications-button"
            type="button"
            disabled
            aria-label="Notifications — coming later"
            title="Notifications — coming later"
          >
            <Icon name="alerts" />
          </button>
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
