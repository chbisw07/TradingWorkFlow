"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

export function ScannerHistoryMenu({
  onRecent,
  onHistory,
}: {
  onRecent: () => void;
  onHistory: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const firstItem = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    firstItem.current?.focus();
    const closeOutside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    setOpen(false);
    trigger.current?.focus();
  }

  function choose(action: () => void) {
    setOpen(false);
    action();
  }

  return (
    <div className="sc-history-menu" ref={root} onKeyDown={onKeyDown}>
      <button
        type="button"
        ref={trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        Scan History ▾
      </button>
      {open && (
        <div
          role="menu"
          aria-label="Scan History"
          className="sc-history-options"
        >
          <button
            ref={firstItem}
            role="menuitem"
            onClick={() => choose(onRecent)}
          >
            Recent Scans
          </button>
          <button role="menuitem" onClick={() => choose(onHistory)}>
            Scan History
          </button>
        </div>
      )}
    </div>
  );
}
