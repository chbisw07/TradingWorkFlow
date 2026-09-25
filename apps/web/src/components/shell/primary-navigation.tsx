"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { Icon, type IconName } from "./icon";

export const navigationItems: { label: string; icon: IconName }[] = [
  { label: "Home", icon: "home" },
  { label: "Watchlists", icon: "watchlists" },
  { label: "Scanners", icon: "scanners" },
  { label: "Candidates", icon: "candidates" },
  { label: "Positions", icon: "positions" },
  { label: "Orders", icon: "orders" },
  { label: "Alerts", icon: "alerts" },
  { label: "Consoles", icon: "consoles" },
  { label: "History", icon: "history" },
  { label: "Settings", icon: "settings" },
];

export function PrimaryNavigation() {
  const [expanded, setExpanded] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const pathname = usePathname();
  return (
    <nav
      className="primary-nav"
      aria-label="Primary navigation"
      data-expanded={expanded}
      onKeyDown={(event) => {
        if (event.key === "Escape" && expanded) {
          setExpanded(false);
          toggle.current?.focus();
        }
      }}
    >
      <button
        ref={toggle}
        type="button"
        className="nav-toggle"
        aria-expanded={expanded}
        aria-controls="primary-nav-items"
        onClick={() => setExpanded(!expanded)}
      >
        <span>Workspace navigation</span>
        <span aria-hidden="true">{expanded ? "−" : "+"}</span>
      </button>
      <div className="nav-content" id="primary-nav-items">
        <p className="nav-caption">WORKSPACE</p>
        <ul>
          {navigationItems.map(({ label, icon }, index) => (
            <li key={label}>
              {index === 0 || label === "Settings" ? (
                <Link
                  href={label === "Settings" ? "/settings" : "/"}
                  className="nav-item"
                  aria-current={
                    pathname === (label === "Settings" ? "/settings" : "/")
                      ? "page"
                      : undefined
                  }
                  onClick={() => setExpanded(false)}
                >
                  <Icon name={icon} />
                  <span>{label}</span>
                </Link>
              ) : (
                <button
                  type="button"
                  className="nav-item"
                  disabled
                  aria-label={`${label} — coming later`}
                >
                  <Icon name={icon} />
                  <span>{label}</span>
                  <span className="nav-later" aria-hidden="true">
                    Later
                  </span>
                </button>
              )}
            </li>
          ))}
        </ul>
        <p className="nav-note">
          Foundation preview
          <br />
          Trading is not enabled.
        </p>
      </div>
    </nav>
  );
}
