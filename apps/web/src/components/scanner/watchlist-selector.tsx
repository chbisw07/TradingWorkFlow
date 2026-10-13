"use client";

import { useEffect, useRef, useState } from "react";
import { watchlistReadinessLabel, type Watchlist } from "../../lib/watchlists";

type Props = {
  lists: Watchlist[];
  selectedId?: string;
  onSelect: (id: string) => void;
  status?: "loading" | "ready" | "error";
};

export function ScannerWatchlistSelector({
  lists,
  selectedId,
  onSelect,
  status = "ready",
}: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const selected = lists.find((list) => list.id === selectedId);
  const matches = (list: Watchlist) =>
    list.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase());
  const mine = lists
    .filter((list) => list.ownership_kind !== "SYSTEM" && matches(list))
    .sort(
      (a, b) =>
        Number(b.favorite) - Number(a.favorite) || a.name.localeCompare(b.name),
    );
  const system = lists
    .filter((list) => list.ownership_kind === "SYSTEM" && matches(list))
    .sort((a, b) => a.name.localeCompare(b.name));

  useEffect(() => {
    if (!open) return;
    searchInput.current?.focus();
    function outside(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  function choose(id: string) {
    onSelect(id);
    setOpen(false);
    setSearch("");
    trigger.current?.focus();
  }

  return (
    <div
      className="sc-watchlist-selector"
      ref={root}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          setOpen(false);
          trigger.current?.focus();
        }
        if (event.key === "ArrowDown" && open) {
          event.preventDefault();
          const options = Array.from(
            root.current?.querySelectorAll<HTMLButtonElement>(
              ".sc-watchlist-item",
            ) || [],
          );
          options[
            (options.indexOf(document.activeElement as HTMLButtonElement) + 1) %
              options.length
          ]?.focus();
        }
        if (event.key === "ArrowUp" && open) {
          event.preventDefault();
          const options = Array.from(
            root.current?.querySelectorAll<HTMLButtonElement>(
              ".sc-watchlist-item",
            ) || [],
          );
          const index = options.indexOf(
            document.activeElement as HTMLButtonElement,
          );
          options[
            index < 0
              ? options.length - 1
              : (index - 1 + options.length) % options.length
          ]?.focus();
        }
      }}
    >
      <button
        ref={trigger}
        type="button"
        className="sc-watchlist-trigger"
        aria-label={`Watchlist: ${status === "error" ? "Watchlists unavailable" : status === "loading" ? "Loading watchlists" : selected?.name || (selectedId ? "Unavailable watchlist" : "Choose watchlist")}`}
        aria-expanded={open}
        aria-controls="scanner-watchlist-popover"
        onClick={() => setOpen((current) => !current)}
      >
        ◈{" "}
        {status === "error"
          ? "Watchlists unavailable"
          : selected?.name ||
            (selectedId ? "Unavailable watchlist" : "Watchlist")}{" "}
        {selected?.read_only ? "🔒" : ""} ▾
      </button>
      {open && (
        <div
          className="sc-watchlist-popover"
          id="scanner-watchlist-popover"
          role="dialog"
          aria-label="Select Watchlist"
        >
          <strong>Select Watchlist</strong>
          <input
            ref={searchInput}
            aria-label="Search watchlists"
            placeholder="Search watchlists…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {status === "loading" ? (
            <p role="status">Loading watchlists…</p>
          ) : status === "error" ? (
            <p role="alert">Watchlists unavailable. Please retry later.</p>
          ) : (
            <div className="sc-watchlist-scroll">
              <div className="sc-watchlist-group-label">
                My Watchlists <span>{mine.length}</span>
              </div>
              {mine.map((list) => (
                <div className="sc-watchlist-row" key={list.id}>
                  <button
                    type="button"
                    className="sc-watchlist-item"
                    aria-current={selectedId === list.id ? "true" : undefined}
                    onClick={() => choose(list.id)}
                  >
                    {list.name} ({list.count})
                  </button>
                </div>
              ))}
              {!mine.length && <small>No matching personal watchlists.</small>}
              <div className="sc-watchlist-group-label">
                Built-in Watchlists <span>{system.length}</span>
              </div>
              {system.map((list) => (
                <button
                  type="button"
                  key={list.id}
                  className="sc-watchlist-item sc-watchlist-system"
                  aria-current={selectedId === list.id ? "true" : undefined}
                  aria-label={`${list.name}, ${list.count} constituents, built-in read-only${watchlistReadinessLabel(list) ? `, ${watchlistReadinessLabel(list)}` : ""}`}
                  disabled={!list.enabled}
                  title={watchlistReadinessLabel(list) || list.description}
                  onClick={() => choose(list.id)}
                >
                  <span>
                    {list.name} ({list.count})
                    {watchlistReadinessLabel(list) && (
                      <small className="sc-watchlist-readiness">
                        {watchlistReadinessLabel(list)}
                      </small>
                    )}
                  </span>
                  <span aria-hidden="true">🔒</span>
                </button>
              ))}
              {!system.length && (
                <small>No matching built-in watchlists.</small>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
