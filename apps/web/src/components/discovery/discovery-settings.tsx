"use client";

import { useEffect, useState } from "react";
import {
  discoveryApi,
  type DiscoverySettings,
  type ProviderChoice,
} from "../../lib/discovery";
import { SurfaceState } from "../ui/surface-state";

export function DiscoverySettingsSection() {
  const [current, setCurrent] = useState<DiscoverySettings | null>(null);
  const [draft, setDraft] = useState<DiscoverySettings | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setError("");
    try {
      const value = await discoveryApi<DiscoverySettings>("settings");
      setCurrent(value);
      setDraft(value);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  useEffect(() => {
    let active = true;
    discoveryApi<DiscoverySettings>("settings")
      .then((value) => {
        if (!active) return;
        setCurrent(value);
        setDraft(value);
      })
      .catch((reason: unknown) => {
        if (active) setError((reason as Error).message);
      });
    return () => {
      active = false;
    };
  }, []);

  async function save() {
    if (!draft) return;
    setPending(true);
    setError("");
    setNotice("");
    try {
      const value = await discoveryApi<DiscoverySettings>(
        "settings",
        "PUT",
        draft,
      );
      setCurrent(value);
      setDraft(value);
      setNotice("Scan & Discover defaults saved.");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="discovery-settings-heading">
      <h2 id="discovery-settings-heading">Scan &amp; Discover</h2>
      <p>
        Choose your default discovery source, scan profile, evidence freshness,
        history retention, and optional AI explanation.
      </p>
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => void load()}>
            Reload discovery settings
          </button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {!draft && !error && (
        <SurfaceState
          state="LOADING"
          headingLevel={3}
          title="Loading discovery settings"
          description="Reading your discovery defaults."
        />
      )}
      {draft && (
        <fieldset className="discovery-settings" disabled={pending}>
          <legend>Discovery defaults · Revision {draft.revision}</legend>
          <div className="discovery-settings-grid">
            <section aria-labelledby="settings-general-heading">
              <h3 id="settings-general-heading">General</h3>
              <label htmlFor="discovery-horizon">Default horizon</label>
              <select
                id="discovery-horizon"
                value={draft.default_horizon}
                onChange={(event) =>
                  setDraft({ ...draft, default_horizon: event.target.value })
                }
              >
                <option value="intraday">Intraday</option>
                <option value="1d">1 day</option>
                <option value="5d">5 days</option>
                <option value="15d">15 days</option>
              </select>
            </section>

            <section aria-labelledby="settings-providers-heading">
              <h3 id="settings-providers-heading">Providers</h3>
              <label htmlFor="discovery-provider">Default provider</label>
              <select
                id="discovery-provider"
                value={draft.default_provider}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    default_provider: event.target.value as ProviderChoice,
                  })
                }
              >
                <option value="internal">
                  Internal Scanner V0 · synthetic
                </option>
                <option value="tradingview-synthetic">
                  TradingView adapter · synthetic
                </option>
              </select>
              <small>
                Provider mode remains visible in the scan workspace.
              </small>
            </section>

            <section aria-labelledby="settings-profiles-heading">
              <h3 id="settings-profiles-heading">Scan profiles</h3>
              <label htmlFor="discovery-profile">Default scan profile</label>
              <select
                id="discovery-profile"
                value={draft.default_profile}
                onChange={(event) =>
                  setDraft({ ...draft, default_profile: event.target.value })
                }
              >
                <option value="RELATIVE_VOLUME">Relative volume</option>
                <option value="TREND_CONTINUATION">Trend continuation</option>
                <option value="BREAKOUT_WITH_VOLUME">
                  Breakout with volume
                </option>
                <option value="PULLBACK_IN_UPTREND">Pullback in uptrend</option>
                <option value="MOMENTUM">Momentum</option>
              </select>
            </section>

            <section aria-labelledby="settings-freshness-heading">
              <h3 id="settings-freshness-heading">Freshness</h3>
              <label htmlFor="discovery-freshness">
                Evidence freshness window (seconds)
              </label>
              <input
                id="discovery-freshness"
                type="number"
                min={60}
                max={86400}
                value={draft.freshness_seconds}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    freshness_seconds: Number(event.target.value),
                  })
                }
              />
              <small>
                Missing source time is shown separately from stale evidence.
              </small>
            </section>

            <section aria-labelledby="settings-llm-heading">
              <h3 id="settings-llm-heading">LLM</h3>
              <label className="settings-check" htmlFor="discovery-llm">
                <input
                  id="discovery-llm"
                  type="checkbox"
                  checked={draft.llm_enabled}
                  onChange={(event) =>
                    setDraft({ ...draft, llm_enabled: event.target.checked })
                  }
                />
                <span>Enable optional AI explanation</span>
              </label>
              <small>
                The current synthetic explainer can summarize grounded evidence.
                It cannot score, transition, recommend, or trade.
              </small>
            </section>

            <section aria-labelledby="settings-history-heading">
              <h3 id="settings-history-heading">History / retention</h3>
              <div className="settings-inline-grid">
                <label htmlFor="discovery-retention">
                  Retention (days)
                  <input
                    id="discovery-retention"
                    type="number"
                    min={7}
                    max={3650}
                    value={draft.retention_days}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        retention_days: Number(event.target.value),
                      })
                    }
                  />
                </label>
                <label htmlFor="discovery-history">
                  History limit
                  <input
                    id="discovery-history"
                    type="number"
                    min={5}
                    max={200}
                    value={draft.max_history_items}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        max_history_items: Number(event.target.value),
                      })
                    }
                  />
                </label>
              </div>
            </section>
          </div>

          <details className="settings-advanced">
            <summary>Advanced relevance and experimental settings</summary>
            <div className="settings-inline-grid">
              <label htmlFor="discovery-low-band">
                Low band upper bound
                <input
                  id="discovery-low-band"
                  type="number"
                  min={0}
                  max={1}
                  step="0.01"
                  value={draft.low_max}
                  onChange={(event) =>
                    setDraft({ ...draft, low_max: event.target.value })
                  }
                />
              </label>
              <label htmlFor="discovery-medium-band">
                Medium band upper bound
                <input
                  id="discovery-medium-band"
                  type="number"
                  min={0}
                  max={1}
                  step="0.01"
                  value={draft.medium_max}
                  onChange={(event) =>
                    setDraft({ ...draft, medium_max: event.target.value })
                  }
                />
              </label>
            </div>
            <p>
              These bounds label deterministic attention scores. They do not
              estimate probability or change trading authority.
            </p>
          </details>

          <div className="settings-actions">
            <button type="button" onClick={() => void save()}>
              Save discovery defaults
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(current);
                setNotice("Unsaved discovery edits discarded.");
              }}
            >
              Cancel discovery edits
            </button>
          </div>
        </fieldset>
      )}
    </section>
  );
}
