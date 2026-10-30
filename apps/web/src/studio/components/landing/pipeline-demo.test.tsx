// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { installDomFakes, setReducedMotion } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";
import { PipelineDemo } from "./pipeline-demo";

const STEP_MS = 1900;

beforeAll(() => {
  installDomFakes();
});

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  setReducedMotion(false);
});

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

function graph(container: HTMLElement): Element | null {
  return container.querySelector("[data-pipeline-axis]");
}

describe("PipelineDemo", () => {
  it("plays the example run step by step", () => {
    renderStudio(<PipelineDemo />);
    expect(screen.getByText("Literature is running")).toBeTruthy();
    advance(STEP_MS);
    expect(screen.getByText("Literature is waiting for your review")).toBeTruthy();
    expect(screen.getByText("Literature: Needs review")).toBeTruthy();
  });

  it("freezes on the step it shows when paused, loops included, and goes on from there", () => {
    const { container } = renderStudio(<PipelineDemo />);
    advance(STEP_MS);
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));

    // The same step stays on screen, however long the visitor reads it.
    expect(screen.getByText("Literature is waiting for your review")).toBeTruthy();
    expect(screen.getByText("Literature: Needs review")).toBeTruthy();
    expect(graph(container)?.getAttribute("data-paused")).toBe("true");
    advance(STEP_MS * 10);
    expect(screen.getByText("Literature is waiting for your review")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(graph(container)?.hasAttribute("data-paused")).toBe(false);
    expect(screen.getByText("Literature is waiting for your review")).toBeTruthy();
    advance(STEP_MS);
    expect(screen.getByText("You approved Literature")).toBeTruthy();
  });

  it("shows one still step with reduced motion, and no pause button", () => {
    setReducedMotion(true);
    renderStudio(<PipelineDemo />);
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
    expect(screen.getByText("You approved Coding")).toBeTruthy();
    advance(STEP_MS * 5);
    expect(screen.getByText("You approved Coding")).toBeTruthy();
  });
});
