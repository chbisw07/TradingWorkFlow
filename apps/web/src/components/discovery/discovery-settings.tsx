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
        Owner-scoped defaults for discovery, evidence freshness, history
        retention, and optional narrative explanation.
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
        <fieldset disabled={pending}>
          <legend>Discovery defaults · Revision {draft.revision}</legend>
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
            <option value="internal">Internal Scanner V0</option>
            <option value="tradingview-synthetic">
              TradingView synthetic validation
            </option>
          </select>
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
            <option value="BREAKOUT_WITH_VOLUME">Breakout with volume</option>
            <option value="PULLBACK_IN_UPTREND">Pullback in uptrend</option>
            <option value="MOMENTUM">Momentum</option>
          </select>
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
          <label className="settings-check" htmlFor="discovery-llm">
            <input
              id="discovery-llm"
              type="checkbox"
              checked={draft.llm_enabled}
              onChange={(event) =>
                setDraft({ ...draft, llm_enabled: event.target.checked })
              }
            />
            <span>Enable controlled Level-0 explanation</span>
          </label>
          <p>
            Current implementation uses the synthetic validation explainer. It
            has no scoring, lifecycle, recommendation, or trading authority.
          </p>
          <div className="settings-inline-grid">
            <label htmlFor="discovery-freshness">
              Freshness window (seconds)
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
            </label>
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
