import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { TrendIndicator } from "../src/components/scanner/trend-indicator";

test.each([
  ["Up", "derivative-trend-up", "▲Up"],
  ["DOWN", "derivative-trend-down", "▼Down"],
  [null, "derivative-trend-neutral", "—"],
  ["unexpected", "derivative-trend-neutral", "—"],
])("renders only canonical trend evidence %s", (trend, tone, label) => {
  const { container } = render(<TrendIndicator trend={trend} />);
  expect(container.firstChild).toHaveClass(tone);
  expect(container.firstChild).toHaveTextContent(label);
});

test("does not infer trend from other positive or negative scan evidence", () => {
  render(
    <div
      data-change="+2.5%"
      data-option-type="CE"
      data-oi-interpretation="Call long buildup"
    >
      <TrendIndicator trend={null} />
    </div>,
  );
  expect(screen.getByText("—")).toBeInTheDocument();
});
