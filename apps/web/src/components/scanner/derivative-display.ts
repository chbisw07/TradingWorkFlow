/** UI-only OI labels. Canonical inferred evidence and history stay unchanged. */
export function oiDisplay(label: string | null | undefined): {
  label: string;
  tone: "call-long" | "put-short" | "neutral";
} {
  const visibleLabel = (label || "Insufficient evidence")
    .replace(/^inferred[:\s]+/i, "")
    .replace(/\s+inferred$/i, "");
  // The EWD explicitly highlights these two labels. Other interpretations do
  // not imply a consistent direction from option side alone, so remain neutral.
  const tone =
    visibleLabel === "Call long buildup"
      ? "call-long"
      : visibleLabel === "Put short buildup"
        ? "put-short"
        : "neutral";
  return { label: visibleLabel, tone };
}
