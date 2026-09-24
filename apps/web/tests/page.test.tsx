import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "../src/app/page";

test("renders the current shell target and its bounded scope", () => {
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 1, name: "Workspace overview" }),
  ).toBeInTheDocument();
  expect(screen.getByText("TWF-1.1 Frontend Shell")).toBeInTheDocument();
  expect(screen.getByText("TWF-1.2 Backend Shell")).toBeInTheDocument();
});
