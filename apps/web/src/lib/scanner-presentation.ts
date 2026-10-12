import { filterExpression, type Catalog, type ScanRow } from "./scanner";

// A match is decided by the technical predicates. Ranking only qualifies its
// presentation; it must never become the reason a row claims to have matched.
export function conciseMatchReason(
  row: ScanRow,
  catalog: Catalog | null,
): string {
  const passed = row.diagnostics?.find((item) => item.passed === true);
  if (!passed) return "Matched filters";

  const { filter, observed } = passed;
  let technical = filterExpression(filter, catalog);
  if (filter.field === "trend" && typeof observed === "string") {
    technical = `Trend ${observed}`;
  } else if (filter.field === "rsi" && typeof observed === "number") {
    if (filter.operator === "<" && observed < 30) technical = "RSI Oversold";
    if (filter.operator === ">" && observed > 70) technical = "RSI Overbought";
  }

  const classification = row.analysis?.context_classification;
  const adjustment = row.analysis?.context_adjustment ?? 0;
  return classification === "SUPPORTIVE" && adjustment > 0
    ? `${technical} · Supportive`
    : technical;
}
