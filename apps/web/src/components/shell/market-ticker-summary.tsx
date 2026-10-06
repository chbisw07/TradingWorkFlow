// A global market feed is not wired yet. Never present demo numbers as live quotes.
const indices = ["NIFTY", "BANKNIFTY", "INDIA VIX"] as const;
export function MarketTickerSummary() {
  return (
    <dl
      className="market-ticker-summary"
      aria-label="Market summary — live values unavailable"
    >
      {indices.map((name) => (
        <div key={name}>
          <dt>{name}</dt>
          <dd>
            <strong aria-label="Value unavailable">—</strong>
            <span>Unavailable</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
