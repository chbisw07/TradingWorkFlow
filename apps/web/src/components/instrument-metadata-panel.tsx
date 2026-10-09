import {
  metadataMarketCap,
  type InstrumentMetadataSummary,
} from "../lib/watchlists";

const value = (item: string | number | null | undefined) => item ?? "—";
const asOf = (item: string | null | undefined) =>
  item
    ? new Date(`${item.slice(0, 10)}T12:00:00+05:30`).toLocaleDateString(
        "en-GB",
        {
          timeZone: "Asia/Kolkata",
          day: "2-digit",
          month: "short",
          year: "numeric",
        },
      )
    : "—";

export function InstrumentMetadataPanel({
  metadata,
}: {
  metadata: InstrumentMetadataSummary | null | undefined;
}) {
  const underlying = metadata?.resolution_basis === "UNDERLYING";
  return (
    <section
      className="instrument-metadata"
      aria-label={
        underlying ? "Underlying instrument metadata" : "Instrument metadata"
      }
    >
      <header>
        <h3>
          {underlying
            ? "Underlying instrument metadata"
            : "Instrument metadata"}
        </h3>
        {metadata && !metadata.present_in_latest_snapshot && (
          <span className="metadata-stale" role="status">
            Stale metadata
          </span>
        )}
      </header>
      {underlying && (
        <p className="metadata-basis">
          Applies to {metadata.metadata_symbol}, the canonical underlying.
        </p>
      )}
      <dl>
        <div>
          <dt>{underlying ? "Underlying sector" : "Sector"}</dt>
          <dd>{value(metadata?.sector)}</dd>
        </div>
        <div>
          <dt>{underlying ? "Underlying industry" : "Industry"}</dt>
          <dd>{value(metadata?.industry)}</dd>
        </div>
        <div>
          <dt>Market cap</dt>
          <dd>{metadataMarketCap(metadata)}</dd>
        </div>
        <div>
          <dt>NSE size band</dt>
          <dd>{value(metadata?.market_cap_category)}</dd>
        </div>
        <div>
          <dt>TWF analytical tier</dt>
          <dd>{value(metadata?.twf_cap_tier)}</dd>
        </div>
        <div>
          <dt title="Display-only analytical context benchmark">
            Context benchmark
          </dt>
          <dd>{value(metadata?.context_benchmark)}</dd>
        </div>
        <div>
          <dt>Market-cap rank</dt>
          <dd>{value(metadata?.market_cap_rank)}</dd>
        </div>
        <div>
          <dt>Classification as of</dt>
          <dd>
            {asOf(
              metadata?.market_cap_as_of ||
                metadata?.industry_as_of ||
                metadata?.sector_as_of,
            )}
          </dd>
        </div>
      </dl>
      {!metadata && (
        <small>
          Authoritative metadata is unavailable for this instrument.
        </small>
      )}
      {metadata && !metadata.present_in_latest_snapshot && (
        <small>
          Last-known values are retained because this instrument is absent from
          the latest imported snapshot.
        </small>
      )}
    </section>
  );
}
