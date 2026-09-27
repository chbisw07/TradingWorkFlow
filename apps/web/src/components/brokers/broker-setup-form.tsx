"use client";
import { useRef, useState, type FormEvent } from "react";
import {
  isSecretField,
  validCredentialManifest,
  type BrokerProviderManifest,
} from "../../lib/broker-setup";
export type SetupInput = { label: string; credentials: Record<string, string> };
/** Collects ephemeral inputs. It neither stores credentials nor chooses provider API operations. */
export function BrokerSetupForm({
  manifest,
  label = "",
  lockedLabel = false,
  onSubmit,
}: {
  manifest: BrokerProviderManifest;
  label?: string;
  lockedLabel?: boolean;
  onSubmit: (input: SetupInput) => Promise<void>;
}) {
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  if (!validCredentialManifest(manifest))
    return <p role="status">Setup is not available for this broker.</p>;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setFailed(false);
    const form = event.currentTarget;
    const values = new FormData(form);
    const input: SetupInput = {
      label: String(values.get("label") || "").trim(),
      credentials: {},
    };
    for (const field of manifest.credential_fields) {
      input.credentials[field.key] = String(values.get(field.key) || "");
      const control = form.elements.namedItem(field.key);
      if (control instanceof HTMLInputElement) control.value = "";
      values.delete(field.key);
    }
    try {
      await onSubmit(input);
    } catch {
      setFailed(true);
    } finally {
      // No credentials survive in component state, DOM or a retained submission object.
      for (const key of Object.keys(input.credentials))
        delete input.credentials[key];
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <form
      className="broker-credential-form"
      aria-label={`Setup ${manifest.display_name}`}
      onSubmit={(event) => void submit(event)}
    >
      <label>
        Connection name
        <input
          name="label"
          defaultValue={label}
          readOnly={lockedLabel}
          required
          minLength={1}
          maxLength={80}
          autoComplete="off"
          placeholder="Primary"
        />
      </label>
      {[...manifest.credential_fields]
        .sort((a, b) => a.order - b.order)
        .map((field) => (
          <label key={field.key}>
            {field.label}
            <input
              name={field.key}
              type={isSecretField(field) ? "password" : "text"}
              required={field.required}
              autoComplete={
                field.kind === "TOTP_CODE"
                  ? "one-time-code"
                  : isSecretField(field)
                    ? "new-password"
                    : "off"
              }
              inputMode={field.kind === "TOTP_CODE" ? "numeric" : undefined}
              placeholder={field.placeholder}
              minLength={field.validation?.minLength}
              maxLength={field.validation?.maxLength}
              pattern={field.validation?.pattern}
              spellCheck={false}
              autoCapitalize="none"
            />
          </label>
        ))}
      <p className="panel-intro">
        Credentials are cleared from this form when you save.
      </p>
      <button className="quiet-button" type="submit" disabled={busy}>
        {busy ? "Saving…" : "Save configuration"}
      </button>
      {failed && (
        <p role="alert">
          Could not save configuration. Check the connection and try again.
        </p>
      )}
    </form>
  );
}
