"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

export type DerivativeTemplate = {
  template_id: string;
  name: string;
  scanner_type: "DERIVATIVES";
  instrument_scope: "OPTIONS" | "FUTURES";
  horizon: "INTRADAY" | "POSITIONAL" | "GENERAL";
  source: "BUILT_IN" | "USER";
  description: string;
  template_schema_version: number;
  recipe: {
    scanner_type: "DERIVATIVES";
    instrument_scope: "OPTIONS" | "FUTURES";
    expiry_mode: "NEAREST" | "EXACT";
    exact_expiry: string | null;
    strike_window: 5 | 10 | 15 | 20;
    watchlist_id: string | null;
    predicates: {
      field: string;
      operator: string;
      value: string | number | number[] | string[];
    }[];
  };
};

export function DerivativeTemplateMenu({
  builtIn,
  user,
  onLoad,
  onRename,
  onDelete,
}: {
  builtIn: DerivativeTemplate[];
  user: DerivativeTemplate[];
  onLoad: (template: DerivativeTemplate) => void;
  onRename: (template: DerivativeTemplate) => void;
  onDelete: (template: DerivativeTemplate) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    first.current?.focus();
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
  function choose(template: DerivativeTemplate) {
    setOpen(false);
    onLoad(template);
  }
  return (
    <div className="sc-template-menu" ref={root} onKeyDown={keyDown}>
      <button
        type="button"
        ref={trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        Scan Templates ▾
      </button>
      {open && (
        <div
          className="sc-template-options"
          role="menu"
          aria-label="Scan Templates"
        >
          <strong>Scan Templates</strong>
          {(["INTRADAY", "POSITIONAL"] as const).map((horizon) => (
            <section
              key={horizon}
              aria-label={horizon === "INTRADAY" ? "Intraday" : "Positional"}
            >
              <h3>{horizon === "INTRADAY" ? "⚡ Intraday" : "◷ Positional"}</h3>
              {builtIn
                .filter((item) => item.horizon === horizon)
                .map((item, index) => (
                  <button
                    key={item.template_id}
                    ref={
                      horizon === "INTRADAY" && index === 0 ? first : undefined
                    }
                    role="menuitem"
                    type="button"
                    onClick={() => choose(item)}
                    title={item.description}
                  >
                    <span>{item.name}</span>
                    <small>{item.description} · Options</small>
                  </button>
                ))}
            </section>
          ))}
          <section aria-label="My Templates">
            <h3>♙ My Templates ({user.length})</h3>
            {user.length === 0 && <p>No templates saved yet.</p>}
            {user.map((item) => (
              <div key={item.template_id} className="sc-template-user-row">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => choose(item)}
                  title={item.description}
                >
                  <span>{item.name}</span>
                  <small>
                    {item.horizon.toLowerCase()} ·{" "}
                    {item.description || "Options configuration"}
                  </small>
                </button>
                <button
                  type="button"
                  aria-label={`Rename ${item.name}`}
                  onClick={() => {
                    setOpen(false);
                    onRename(item);
                  }}
                >
                  Rename
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${item.name}`}
                  onClick={() => {
                    setOpen(false);
                    onDelete(item);
                  }}
                >
                  Delete
                </button>
              </div>
            ))}
          </section>
        </div>
      )}
    </div>
  );
}
