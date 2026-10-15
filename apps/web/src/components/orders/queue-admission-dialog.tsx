"use client";

import { useEffect, useRef } from "react";
import type { TWFOrder } from "../../lib/twf-orders";

export function QueueAdmissionDialog({
  order,
  busy,
  onCancel,
  onConfirm,
}: {
  order: TWFOrder;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const confirm = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    confirm.current?.focus();
    return () => previous?.focus();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="order-dialog twf-queue-confirm"
      aria-labelledby="twf-queue-confirm-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onCancel();
      }}
    >
      <header className="order-titlebar">
        <h2 id="twf-queue-confirm-title">Add to TWF Queue</h2>
        <button
          aria-label="Close confirmation"
          disabled={busy}
          onClick={onCancel}
        >
          ×
        </button>
      </header>
      <div className="twf-queue-confirm-body">
        <p>Add this READY TWF Order to TWF Queue?</p>
        <dl className="orders-facts">
          <div>
            <dt>Order ID</dt>
            <dd>{order.twf_order_id}</dd>
          </div>
          <div>
            <dt>Instrument</dt>
            <dd>{order.instrument.symbol}</dd>
          </div>
          <div>
            <dt>Side</dt>
            <dd>{order.terms.side}</dd>
          </div>
          <div>
            <dt>Quantity</dt>
            <dd>{order.terms.quantity}</dd>
          </div>
          <div>
            <dt>Order type</dt>
            <dd>{order.terms.order_type}</dd>
          </div>
        </dl>
        <p className="orders-boundary">
          This does not submit an order to the broker.
        </p>
      </div>
      <footer className="twf-queue-confirm-actions">
        <button disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button
          ref={confirm}
          className="primary"
          disabled={busy}
          onClick={onConfirm}
        >
          {busy ? "Adding…" : "Add to Queue"}
        </button>
      </footer>
    </dialog>
  );
}
