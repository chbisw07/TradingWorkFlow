"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./icon";
import { navigationSections, type NavigationItem } from "./navigation";
import { useLocationHash } from "./use-location-hash";
import { version } from "../../../package.json";

function SidebarItem({
  item,
  active,
  onNavigate,
}: {
  item: NavigationItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  const contents = (
    <>
      <Icon name={item.icon} />
      <span>{item.label}</span>
    </>
  );
  // Native anchors keep hashchange, focus and same-page Settings navigation reliable.
  return (
    <li>
      {item.href.includes("#") ? (
        <a
          href={item.href}
          className="nav-item"
          aria-current={active ? "page" : undefined}
          onClick={onNavigate}
        >
          {contents}
        </a>
      ) : (
        <Link
          href={item.href}
          className="nav-item"
          aria-current={active ? "page" : undefined}
          onClick={onNavigate}
        >
          {contents}
        </Link>
      )}
    </li>
  );
}
export function PrimaryNavigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const hash = useLocationHash();
  return (
    <nav className="primary-nav" aria-label="Primary navigation">
      <div className="nav-content">
        {navigationSections.map((section) => (
          <section
            className="sidebar-section"
            key={section.label}
            aria-label={section.label}
          >
            <h2 className="nav-caption">{section.label}</h2>
            <ul>
              {section.items.map((item) => {
                const [route, anchor] = item.href.split("#");
                const active = anchor
                  ? pathname === route &&
                    (hash || "#preferences") === `#${anchor}`
                  : route === "/"
                    ? pathname === "/"
                    : pathname === route || pathname.startsWith(route + "/");
                return (
                  <SidebarItem
                    key={item.href}
                    item={item}
                    active={active}
                    onNavigate={onNavigate}
                  />
                );
              })}
            </ul>
          </section>
        ))}
      </div>
      <footer className="sidebar-footer">
        <div>
          <span className="brand-mark" aria-hidden="true">
            twf<span>.</span>
          </span>
          <span>v{version}</span>
        </div>
        <p>© 2026 TradingWorkFlow</p>
        <p>Scan. Discover. Trade Smarter.</p>
      </footer>
    </nav>
  );
}
