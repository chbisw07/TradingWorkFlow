"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

export function DerivativeSaveMenu({
  onSaveScan,
  onSaveTemplate,
}: {
  onSaveScan: () => void;
  onSaveTemplate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);
  function keyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const items = Array.from(
        root.current?.querySelectorAll<HTMLButtonElement>(
          '[role="menuitem"]',
        ) || [],
      );
      if (!items.length) return;
      event.preventDefault();
      const current = items.indexOf(
        document.activeElement as HTMLButtonElement,
      );
      const step = event.key === "ArrowDown" ? 1 : -1;
      const next =
        current === -1
          ? step === 1
            ? 0
            : items.length - 1
          : (current + step + items.length) % items.length;
      items[next].focus();
    }
  }
  return (
    <div className="sc-save-menu" ref={root} onKeyDown={keyDown}>
      <button
        className="wl-primary"
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        ＋ Save Scan ▾
      </button>
      {open && (
        <div className="sc-save-options" role="menu" aria-label="Save">
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false);
              onSaveScan();
            }}
          >
            <strong>Save Scan</strong>
            <small>Preserve the current scan setup.</small>
          </button>
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false);
              onSaveTemplate();
            }}
          >
            <strong>Save as Template</strong>
            <small>Store only reusable configuration.</small>
          </button>
        </div>
      )}
    </div>
  );
}
