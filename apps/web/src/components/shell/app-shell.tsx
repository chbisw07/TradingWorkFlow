"use client";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { TopBar } from "./top-bar";
import { PrimaryNavigation } from "./primary-navigation";
import { WorkspaceFrame } from "./workspace-frame";
import { Icon } from "./icon";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const focused =
    pathname.startsWith("/brokers") ||
    pathname.startsWith("/watchlists") ||
    pathname.startsWith("/scanners") ||
    pathname.startsWith("/candidates");
  const drawer = useRef<HTMLDialogElement>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  function closeNavigation() {
    drawer.current?.close();
    setNavigationOpen(false);
  }
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1200px)");
    function resize() {
      if (desktop.matches) {
        drawer.current?.close();
        setNavigationOpen(false);
      }
    }
    desktop.addEventListener("change", resize);
    return () => desktop.removeEventListener("change", resize);
  }, []);
  return (
    <div
      className={`app-shell redesigned-shell${focused ? " focused-shell" : ""}`}
    >
      <a className="skip-link" href="#workspace">
        Skip to workspace
      </a>
      <TopBar
        navigationOpen={navigationOpen}
        onOpenNavigation={() => {
          drawer.current?.showModal();
          setNavigationOpen(true);
        }}
      />
      <div className="shell-grid">
        <div className="desktop-sidebar">
          <PrimaryNavigation />
        </div>
        <WorkspaceFrame focused={focused}>{children}</WorkspaceFrame>
      </div>
      <dialog
        ref={drawer}
        id="mobile-navigation"
        className="navigation-drawer"
        aria-label="Workspace navigation"
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const controls = Array.from(
            event.currentTarget.querySelectorAll<HTMLElement>(
              "button:not(:disabled), a[href], [tabindex='0']",
            ),
          );
          const first = controls[0];
          const last = controls[controls.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
          }
        }}
        onClose={() => setNavigationOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) closeNavigation();
        }}
      >
        <div className="drawer-content">
          <div className="drawer-heading">
            <span>Workspace</span>
            <button
              type="button"
              className="shell-icon-button"
              aria-label="Close navigation"
              onClick={closeNavigation}
            >
              <Icon name="close" />
            </button>
          </div>
          <PrimaryNavigation onNavigate={closeNavigation} />
        </div>
      </dialog>
    </div>
  );
}
