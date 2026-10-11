"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

export function ScannerColumnsMenu({
  options,
  selected,
  onChange,
}: {
  options: readonly (readonly [string, string])[];
  selected: readonly string[];
  onChange: (key: string, checked: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<"above" | "below">("below");
  const [maxHeight, setMaxHeight] = useState(320);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const popupId = useId();

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    const measure = () => {
      if (!trigger.current) return;
      const rect = trigger.current.getBoundingClientRect();
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const nextPlacement = below < 240 && above > below ? "above" : "below";
      setPlacement(nextPlacement);
      setMaxHeight(
        Math.max(0, Math.min(320, nextPlacement === "above" ? above : below)),
      );
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [open]);

  return (
    <div className="sc-columns-menu" ref={root} data-placement={placement}>
      <button
        type="button"
        ref={trigger}
        aria-expanded={open}
        aria-controls={popupId}
        onClick={() => setOpen((value) => !value)}
      >
        Columns
      </button>
      {open && (
        <div
          id={popupId}
          className="sc-columns-options"
          role="group"
          aria-label="Visible result columns"
          style={{ maxHeight }}
        >
          {options.map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={selected.includes(key)}
                onChange={(event) => onChange(key, event.target.checked)}
              />
              {label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
