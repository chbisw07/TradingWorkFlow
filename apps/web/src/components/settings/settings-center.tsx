"use client";
import { useEffect, useState, type FormEvent } from "react";
import { SurfaceState } from "../ui/surface-state";

type Values = {
  density?: "comfortable" | "compact";
  default_horizon?: "5d" | "15d";
};
type Snapshot = {
  revision: number;
  overrides: Values;
  effective: Required<Values>;
  sources: Record<keyof Values, "USER" | "PLATFORM">;
  active_profile_id: string | null;
  applied_profile_revision: number | null;
};
type Profile = { id: string; name: string; revision: number; values: Values };
async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api/v1/settings/" + path, {
    method,
    cache: "no-store",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(
      response.status === 409
        ? "These settings changed elsewhere. Reload current values before saving again."
        : response.status === 401
          ? "Your session has expired. Sign in again."
          : response.status === 403
            ? "You do not have permission to change these settings."
            : response.status === 422
              ? "Check the profile name and allowed setting values. No changes were saved."
              : "Settings are unavailable. No success was confirmed; reload before retrying.",
    );
  }
  return response.json() as Promise<T>;
}
export function SettingsCenter() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [draft, setDraft] = useState<Values>({});
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Profile | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api<Snapshot>("values"), api<Profile[]>("profiles")])
      .then(([s, p]) => {
        if (active) {
          setSnapshot(s);
          setDraft(s.overrides);
          setProfiles(p);
        }
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, []);
  async function run(action: () => Promise<void>) {
    setPending(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  async function reload() {
    await run(async () => {
      const [s, p] = await Promise.all([
        api<Snapshot>("values"),
        api<Profile[]>("profiles"),
      ]);
      setSnapshot(s);
      setDraft(s.overrides);
      setProfiles(p);
      setSelected(null);
      setName("");
      setNotice("Current values loaded. Unsaved edits were discarded.");
    });
  }
  async function write(action: "values" | "reset" | "deactivate") {
    if (!snapshot) return;
    await run(async () => {
      const s = await api<Snapshot>(
        action,
        action === "values" ? "PUT" : "POST",
        {
          revision: snapshot.revision,
          ...(action === "values" ? { values: draft } : {}),
        },
      );
      setSnapshot(s);
      setDraft(s.overrides);
      setSelected(null);
      setName("");
      setNotice(
        action === "reset"
          ? "Defaults restored."
          : action === "deactivate"
            ? "Profile detached. Applied values are retained as personal preferences."
            : "Preferences saved and applied.",
      );
    });
  }
  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      const p = await api<Profile>(
        selected ? "profiles/" + selected.id : "profiles",
        selected ? "PUT" : "POST",
        {
          name,
          values: draft,
          ...(selected ? { revision: selected.revision } : {}),
        },
      );
      setProfiles((previous) => [...previous.filter((x) => x.id !== p.id), p]);
      setSelected(p);
      setName(p.name);
      setNotice(
        "Profile saved and validated. Apply it explicitly to change your preferences.",
      );
    });
  }
  async function applyProfile(p: Profile) {
    if (!snapshot) return;
    await run(async () => {
      const s = await api<Snapshot>("profiles/" + p.id + "/apply", "POST", {
        revision: snapshot.revision,
        profile_revision: p.revision,
      });
      setSnapshot(s);
      setDraft(s.overrides);
      setNotice(
        "Profile applied. Future edits require another explicit apply.",
      );
    });
  }
  return (
    <div
      className="settings-center"
      data-density={snapshot?.effective.density || "comfortable"}
    >
      <header>
        <p className="eyebrow">SETUP / PERSONAL PREFERENCES</p>
        <h1>Settings</h1>
        <p>Your preferences, with explicit defaults and saved profiles.</p>
      </header>
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button disabled={pending} onClick={reload}>
            Reload current values
          </button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {!snapshot && !error && (
        <SurfaceState
          state="LOADING"
          headingLevel={2}
          title="Loading preferences"
          description="Reading your saved values."
        />
      )}
      {snapshot && (
        <>
          <section aria-labelledby="preferences-heading">
            <h2 id="preferences-heading">Personal preferences</h2>
            <p>
              Owner: your signed-in user · Scope: User · Revision{" "}
              {snapshot.revision}
            </p>
            <fieldset disabled={pending}>
              <legend>Appearance and workflow defaults</legend>
              <label htmlFor="density">Setup density</label>
              <select
                id="density"
                value={draft.density || ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    density: (e.target.value || undefined) as Values["density"],
                  })
                }
              >
                <option value="">Inherit comfortable</option>
                <option value="comfortable">Comfortable</option>
                <option value="compact">Compact</option>
              </select>
              <p>
                Effective: {snapshot.effective.density} · Source:{" "}
                {snapshot.sources.density === "USER"
                  ? "Personal override"
                  : "Platform default"}
              </p>
              <label htmlFor="horizon">Default analysis horizon</label>
              <select
                id="horizon"
                value={draft.default_horizon || ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    default_horizon: (e.target.value ||
                      undefined) as Values["default_horizon"],
                  })
                }
              >
                <option value="">Inherit 5 trading days</option>
                <option value="5d">5 trading days</option>
                <option value="15d">15 trading days</option>
              </select>
              <p>
                Effective: {snapshot.effective.default_horizon} · Source:{" "}
                {snapshot.sources.default_horizon === "USER"
                  ? "Personal override"
                  : "Platform default"}
              </p>
              <p>
                This default is reserved for future analysis. It does not start
                analysis or change trading authority.
              </p>
              <div className="settings-actions">
                <button onClick={() => write("values")}>
                  Save and apply preferences
                </button>
                <button
                  onClick={() => {
                    setDraft(snapshot.overrides);
                    setSelected(null);
                    setName("");
                    setNotice("Unsaved edits discarded.");
                  }}
                >
                  Cancel edits
                </button>
                <button onClick={() => write("reset")}>
                  Reset preferences to defaults
                </button>
              </div>
            </fieldset>
            <p>
              Theme is a device-local preference. Use the top-bar theme toggle;
              it is not saved to your user or these profiles.
            </p>
          </section>
          <section aria-labelledby="profiles-heading">
            <h2 id="profiles-heading">Preference profiles</h2>
            <p>
              A named set of the two preferences above. Saving a profile does
              not apply it.
            </p>
            <form onSubmit={saveProfile}>
              <fieldset disabled={pending}>
                <legend>{selected ? "Edit profile" : "Create profile"}</legend>
                <label htmlFor="profile-name">Profile name</label>
                <input
                  id="profile-name"
                  required
                  maxLength={64}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <div className="settings-actions">
                  <button type="submit">
                    {selected ? "Save profile changes" : "Create profile"}
                  </button>
                  {selected && (
                    <button
                      type="button"
                      onClick={() => {
                        setSelected(null);
                        setName("");
                      }}
                    >
                      New profile
                    </button>
                  )}
                  <button type="button" onClick={() => setDraft({})}>
                    Use inherited defaults in draft
                  </button>
                </div>
              </fieldset>
            </form>
            {profiles.length === 0 && (
              <p>No profiles yet. Create one from your preference draft.</p>
            )}
            <ul className="settings-profiles">
              {profiles.map((p) => (
                <li key={p.id}>
                  <h3>{p.name}</h3>
                  <p>
                    Validated revision {p.revision}
                    {snapshot.active_profile_id === p.id
                      ? " · Applied revision " +
                        snapshot.applied_profile_revision
                      : " · Not applied"}
                  </p>
                  <div className="settings-actions">
                    <button
                      disabled={pending}
                      onClick={() => {
                        setSelected(p);
                        setName(p.name);
                        setDraft(p.values);
                        setNotice(
                          "Profile loaded into the draft. Current preferences are unchanged.",
                        );
                      }}
                    >
                      Edit {p.name}
                    </button>
                    <button disabled={pending} onClick={() => applyProfile(p)}>
                      Apply {p.name}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            {snapshot.active_profile_id && (
              <button disabled={pending} onClick={() => write("deactivate")}>
                Deactivate profile
              </button>
            )}
          </section>
          <section aria-labelledby="later-heading">
            <h2 id="later-heading">Integration settings</h2>
            <p>
              Provider connections, shared account settings and administration
              are unavailable in this foundation. No credentials can be entered
              here.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
