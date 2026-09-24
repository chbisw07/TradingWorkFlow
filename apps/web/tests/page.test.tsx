import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "../src/app/page";

test("renders the application foundation and clearly scoped status", () => {
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 1, name: "TradingWorkFlow" }),
  ).toBeInTheDocument();
  expect(screen.getByText("TWF-1 Application Foundation")).toBeInTheDocument();
  expect(
    screen.getByRole("region", { name: "Development status" }),
  ).toHaveTextContent("TWF-1.0 Repository Scaffold");
});
