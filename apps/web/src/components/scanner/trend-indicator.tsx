/** Shared presentation of archived deterministic direction evidence. */
export function TrendIndicator({
  trend,
}: {
  trend: string | number | null | undefined;
}) {
  const normalized = typeof trend === "string" ? trend.toLowerCase() : "";
  const tone =
    normalized === "up" ? "up" : normalized === "down" ? "down" : "neutral";
  return (
    <span className={`derivative-trend derivative-trend-${tone}`}>
      {tone !== "neutral" && (
        <span aria-hidden="true">{tone === "up" ? "▲" : "▼"}</span>
      )}
      {tone === "neutral" ? "—" : tone === "up" ? "Up" : "Down"}
    </span>
  );
}
