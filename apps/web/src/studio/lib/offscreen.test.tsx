// @vitest-environment jsdom
import { act, cleanup, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AuroraBackground } from "@/studio/components/effects/aurora-background";
import { BorderBeam } from "@/studio/components/effects/border-beam";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { installDomFakes, setReducedMotion } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";

/** An IntersectionObserver the test moves elements in and out of view with. */
const observers = vi.hoisted(() => ({
  all: [] as { callback: IntersectionObserverCallback; targets: Set<Element> }[],
}));

class ControlledObserver {
  readonly root = null;
  readonly rootMargin = "0px";
  readonly thresholds = [0];
  private readonly entry: { callback: IntersectionObserverCallback; targets: Set<Element> };
  constructor(callback: IntersectionObserverCallback) {
    this.entry = { callback, targets: new Set() };
    observers.all.push(this.entry);
  }
  observe(target: Element) {
    this.entry.targets.add(target);
  }
  unobserve(target: Element) {
    this.entry.targets.delete(target);
  }
  disconnect() {
    this.entry.targets.clear();
  }
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

function scroll(visible: boolean) {
  act(() => {
    for (const { callback, targets } of observers.all) {
      const entries = [...targets].map(
        (target) => ({ target, isIntersecting: visible }) as IntersectionObserverEntry,
      );
      if (entries.length > 0) {
        callback(entries, {} as IntersectionObserver);
      }
    }
  });
}

beforeAll(() => {
  installDomFakes();
  vi.stubGlobal("IntersectionObserver", ControlledObserver);
});

afterEach(() => {
  cleanup();
  setReducedMotion(false);
});

describe("looping effects off screen", () => {
  it("mark themselves while out of view, so globals.css pauses their loops", () => {
    const { container } = renderStudio(
      <div>
        <ShimmerButton>Start run</ShimmerButton>
        <PulseDot live label="Running" />
        <span className="relative block">
          <BorderBeam />
        </span>
        <ShimmerSkeleton />
      </div>,
    );
    const looping = [
      screen.getByRole("button", { name: "Start run" }),
      screen.getByText("Running").parentElement as HTMLElement,
      container.querySelector(".studio-beam") as HTMLElement,
      container.querySelector(".studio-skeleton") as HTMLElement,
    ];
    scroll(false);
    for (const element of looping) {
      expect(element.hasAttribute("data-offscreen"), element.className).toBe(true);
    }
    scroll(true);
    for (const element of looping) {
      expect(element.hasAttribute("data-offscreen"), element.className).toBe(false);
    }
  });

  it("are not watched when nothing loops (a still dot, reduced motion)", () => {
    setReducedMotion(true);
    renderStudio(
      <div>
        <PulseDot label="Waiting" />
        <ShimmerButton>Start run</ShimmerButton>
      </div>,
    );
    scroll(false);
    expect(screen.getByText("Waiting").parentElement?.hasAttribute("data-offscreen")).toBe(false);
    expect(screen.getByRole("button", { name: "Start run" }).hasAttribute("data-offscreen")).toBe(
      false,
    );
  });
});

describe("AuroraBackground", () => {
  it("stands still behind working screens and pauses the vivid drift off screen", () => {
    const { container, rerender } = renderStudio(<AuroraBackground />);
    const aurora = container.querySelector(".studio-aurora") as HTMLElement;
    expect(aurora.getAttribute("data-variant")).toBe("subtle");
    // motion's useInView reports a change only after the element was once in view.
    scroll(true);
    scroll(false);
    expect(aurora.hasAttribute("data-paused")).toBe(false);

    rerender(<AuroraBackground variant="vivid" />);
    expect(aurora.getAttribute("data-paused")).toBe("true");
    scroll(true);
    expect(aurora.hasAttribute("data-paused")).toBe(false);
  });
});
