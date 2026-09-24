"use client";

import { useSyncExternalStore } from "react";
import { themeStorageKey } from "../../lib/theme";

function getTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

function subscribe(onChange: () => void) {
  window.addEventListener("twf-theme-change", onChange);
  return () => window.removeEventListener("twf-theme-change", onChange);
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getTheme, () => "dark");
  function toggle() {
    const next = getTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(themeStorageKey, next);
    } catch {
      // The current page can still switch when browser storage is disabled.
    }
    window.dispatchEvent(new Event("twf-theme-change"));
  }
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label="Light theme"
      aria-pressed={theme === "light"}
      title="Toggle light theme"
      onClick={toggle}
    >
      <svg
        aria-hidden="true"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
      </svg>
    </button>
  );
}
