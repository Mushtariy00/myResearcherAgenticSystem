// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { installDomFakes, setReducedMotion } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";
import { AnimatedList } from "./animated-list";
import {
  AnimatedTabs,
  AnimatedTabsList,
  AnimatedTabsPanel,
  AnimatedTabsTab,
} from "./animated-tabs";
import { ConfettiBurst } from "./confetti-burst";
import { Marquee } from "./marquee";
import { NumberTicker } from "./number-ticker";
import { PulseDot } from "./pulse-dot";
import { SpotlightCard } from "./spotlight-card";
import { TiltCard } from "./tilt-card";

const confetti = vi.hoisted(() => vi.fn());
vi.mock("canvas-confetti", () => ({ default: confetti }));

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
  setReducedMotion(false);
  setVisibility("visible");
  confetti.mockReset();
});

describe("Studio effects with reduced motion", () => {
  beforeEach(() => {
    setReducedMotion(true);
  });

  it("PulseDot keeps the dot but drops the pulsing ring", () => {
    const { container } = renderStudio(<PulseDot live label="Running" />);
    expect(container.querySelector(".studio-pulse")).toBeNull();
    expect(screen.getByText("Running")).toBeTruthy();
  });

  it("Marquee stands still: one copy, wrapped, nothing moving", () => {
    const { container } = renderStudio(
      <Marquee label="Sources">
        <li>arXiv</li>
        <li>OpenAlex</li>
      </Marquee>,
    );
    expect(screen.getAllByText("arXiv")).toHaveLength(1);
    expect(container.querySelector(".studio-marquee")?.getAttribute("data-reduced")).toBe("true");
  });

  it("TiltCard does not tilt", () => {
    const { container } = renderStudio(
      <TiltCard>
        <p>Card</p>
      </TiltCard>,
    );
    const wrapper = container.querySelector("[data-tilt]");
    expect(wrapper?.getAttribute("data-tilt")).toBe("off");
    const inner = wrapper?.firstElementChild as HTMLElement;
    fireEvent.pointerMove(inner, { pointerType: "mouse", clientX: 10, clientY: 10 });
    expect(inner.style.transform).toBe("");
  });

  it("SpotlightCard leaves the highlight hidden", () => {
    const { container } = renderStudio(<SpotlightCard>Project</SpotlightCard>);
    const card = screen.getByText("Project");
    fireEvent.pointerMove(card, { pointerType: "mouse", clientX: 20, clientY: 20 });
    const spot = container.querySelector("[data-spotlight]") as HTMLElement;
    expect(spot.style.opacity).toBe("");
    expect(spot.style.transform).toBe("");
  });

  it("NumberTicker shows the final value at once", () => {
    renderStudio(<NumberTicker value={1234} />);
    // Visible copy (no counting) and the copy for assistive technology agree.
    expect(screen.getAllByText("1,234").length).toBeGreaterThanOrEqual(2);
  });

  it("ConfettiBurst never fires", async () => {
    const view = renderStudio(<ConfettiBurst when={false} />);
    view.rerender(<ConfettiBurst when />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(confetti).not.toHaveBeenCalled();
  });

  it("AnimatedList still renders every item", () => {
    renderStudio(
      <AnimatedList
        items={["one", "two"]}
        getKey={(item) => item}
        renderItem={(item) => <span>{item}</span>}
        aria-label="Log"
      />,
    );
    expect(screen.getByRole("list", { name: "Log" }).children).toHaveLength(2);
  });
});

describe("Studio effects with motion allowed", () => {
  it("PulseDot pulses while live, and only then", () => {
    const { container, rerender } = renderStudio(<PulseDot live />);
    expect(container.querySelector(".studio-pulse")).not.toBeNull();
    rerender(<PulseDot live={false} />);
    expect(container.querySelector(".studio-pulse")).toBeNull();
  });

  it("Marquee repeats its items for the loop, hidden from assistive technology", () => {
    const { container } = renderStudio(
      <Marquee label="Sources">
        <li>arXiv</li>
      </Marquee>,
    );
    const lists = container.querySelectorAll("ul");
    expect(lists).toHaveLength(2);
    expect(lists[0]?.getAttribute("aria-label")).toBe("Sources");
    expect(lists[1]?.getAttribute("aria-hidden")).toBe("true");
    expect(lists[1]?.hasAttribute("inert")).toBe(true);
  });

  it("SpotlightCard follows a mouse, and only its highlight layer clips (so the glow shows)", () => {
    const { container } = renderStudio(<SpotlightCard>Project</SpotlightCard>);
    const card = screen.getByText("Project");
    const spot = container.querySelector("[data-spotlight]") as HTMLElement;

    fireEvent.pointerMove(card, { pointerType: "touch", clientX: 20, clientY: 20 });
    expect(spot.style.opacity).toBe("");
    fireEvent.pointerMove(card, { pointerType: "mouse", clientX: 20, clientY: 30 });
    expect(spot.style.opacity).toBe("1");
    // Centred on the pointer (jsdom lays nothing out, so the card sits at 0,0).
    expect(spot.style.transform).toMatch(/^translate3d\(-200px, -190px, 0(px)?\)$/);
    fireEvent.pointerLeave(card);
    expect(spot.style.opacity).toBe("0");

    // The hover and focus glow (.studio-lift::after) is drawn outside the card's border box.
    expect(card.className).toMatch(/(^|\s)studio-lift(\s|$)/);
    expect(card.className).not.toMatch(/overflow-(hidden|clip)/);
    expect(spot.parentElement?.className).toMatch(/(^|\s)overflow-hidden(\s|$)/);
  });

  it("TiltCard tilts for a mouse", () => {
    const { container } = renderStudio(
      <TiltCard>
        <p>Card</p>
      </TiltCard>,
    );
    expect(container.querySelector("[data-tilt]")?.getAttribute("data-tilt")).toBe("on");
  });

  it("ConfettiBurst fires once when the goal is reached, never on mount", async () => {
    const view = renderStudio(<ConfettiBurst when />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(confetti).not.toHaveBeenCalled();

    view.rerender(<ConfettiBurst when={false} />);
    view.rerender(<ConfettiBurst when />);
    await waitFor(() => expect(confetti).toHaveBeenCalledTimes(1));
    view.rerender(<ConfettiBurst when />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(confetti).toHaveBeenCalledTimes(1);
  });

  it("AnimatedTabs are real tabs, and the indicator follows the active one", () => {
    renderStudio(
      <AnimatedTabs defaultValue="runs">
        <AnimatedTabsList aria-label="Project">
          <AnimatedTabsTab value="runs">Runs</AnimatedTabsTab>
          <AnimatedTabsTab value="papers">Papers</AnimatedTabsTab>
        </AnimatedTabsList>
        <AnimatedTabsPanel value="runs">Runs panel</AnimatedTabsPanel>
        <AnimatedTabsPanel value="papers">Papers panel</AnimatedTabsPanel>
      </AnimatedTabs>,
    );
    const tablist = screen.getByRole("tablist", { name: "Project" });
    const [runs, papers] = within(tablist).getAllByRole("tab") as [HTMLElement, HTMLElement];
    expect(runs.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel").textContent).toBe("Runs panel");
    expect(runs.querySelector("[aria-hidden]")).not.toBeNull();

    fireEvent.click(papers);
    expect(papers.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel").textContent).toBe("Papers panel");
    expect(papers.querySelector("[aria-hidden]")).not.toBeNull();
    expect(runs.querySelector("[aria-hidden]")).toBeNull();
  });

  it("ConfettiBurst stays quiet while the page is hidden", async () => {
    setVisibility("hidden");
    const view = renderStudio(<ConfettiBurst when={false} />);
    view.rerender(<ConfettiBurst when />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(confetti).not.toHaveBeenCalled();
  });
});
