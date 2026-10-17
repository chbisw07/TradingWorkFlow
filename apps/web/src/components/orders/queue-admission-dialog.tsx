"use client";

import { useEffect, useRef, useState } from "react";
import { twfQueueApi, type QueuePolicy } from "../../lib/twf-queue";
import type { TWFOrder } from "../../lib/twf-orders";

export function QueueAdmissionDialog({
  order,
  accountId = "",
  accountName = "No execution account",
  busy,
  onCancel,
  onConfirm,
}: {
  order: TWFOrder;
  accountId?: string;
  accountName?: string;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [policy, setPolicy] = useState<QueuePolicy | null>(null);
  useEffect(() => {
    let current = true;
    if (accountId)
      void twfQueueApi<QueuePolicy>(`policy/${accountId}`)
        .then((value) => {
          if (current) setPolicy(value);
        })
        .catch(() => {
          if (current) setPolicy(null);
        });
    return () => {
      current = false;
    };
  }, [accountId]);
  const dialog = useRef<HTMLDialogElement>(null);
  const confirm = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    confirm.current?.focus();
    return () => previous?.focus();
  }, []);
  useEffect(() => {
    if (policy?.broker_account_id === accountId) confirm.current?.focus();
  }, [policy, accountId]);
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
          Account: {accountName}. Admission snapshots the account’s current
          dispatch policy.
          {!policy
            ? " Loading admission policy…"
            : policy.current_dispatch_mode === "AUTO"
              ? " AUTO entries may dispatch automatically after fresh checks."
              : " MANUAL entries wait for DISPATCH."}
          {policy && !policy.execution_enabled
            ? " Queue execution is currently disabled by the operator."
            : ""}
        </p>
      </div>
      <footer className="twf-queue-confirm-actions">
        <button disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button
          ref={confirm}
          className="primary"
          disabled={
            busy || !accountId || policy?.broker_account_id !== accountId
          }
          onClick={onConfirm}
        >
          {busy ? "Adding…" : "Add to Queue"}
        </button>
      </footer>
    </dialog>
  );
}
