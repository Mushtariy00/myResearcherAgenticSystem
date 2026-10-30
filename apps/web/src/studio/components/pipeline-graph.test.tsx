// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { installDomFakes } from "@/studio/test/dom";
import { renderStudio } from "@/studio/test/render";
import { PipelineGraph, type PipelineNode } from "./pipeline-graph";

const NODES: PipelineNode[] = [
  { stage: "literature", status: "approved" },
  { stage: "method", status: "running", attempts: 2 },
  { stage: "coding", status: "output_ready" },
  { stage: "experiment", status: "pending" },
  { stage: "writing", status: "skipped" },
];

beforeAll(() => {
  installDomFakes();
});

afterEach(() => {
  cleanup();
});

describe("PipelineGraph", () => {
  it("is an ordered list of the five stages, each with its status as text", () => {
    renderStudio(<PipelineGraph nodes={NODES} />);
    const list = screen.getByRole("list", { name: "Pipeline stages" });
    expect(list.tagName).toBe("OL");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(within(items[0] as HTMLElement).getByText("Literature: Approved")).toBeTruthy();
    expect(within(items[1] as HTMLElement).getByText("Method: Running, Attempt 2")).toBeTruthy();
    expect(within(items[2] as HTMLElement).getByText("Coding: Needs review")).toBeTruthy();
    expect(within(items[3] as HTMLElement).getByText("Experiment: Waiting")).toBeTruthy();
    expect(within(items[4] as HTMLElement).getByText("Writing: Not run")).toBeTruthy();
  });

  it("marks the stages being worked on as the current step", () => {
    renderStudio(<PipelineGraph nodes={NODES} />);
    const current = screen
      .getAllByRole("listitem")
      .filter((item) => item.getAttribute("aria-current") === "step");
    expect(current.map((item) => item.getAttribute("data-stage"))).toEqual(["method", "coding"]);
  });

  it("makes stages focusable buttons that report the chosen stage", () => {
    const onSelect = vi.fn();
    renderStudio(<PipelineGraph nodes={NODES} onSelect={onSelect} selectedStage="method" />);
    const coding = screen.getByRole("button", { name: "Coding: Needs review" });
    coding.focus();
    expect(document.activeElement).toBe(coding);
    fireEvent.click(coding);
    expect(onSelect).toHaveBeenCalledWith("coding");
    expect(
      screen
        .getByRole("button", { name: "Method: Running, Attempt 2" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    expect(coding.getAttribute("aria-pressed")).toBe("false");
  });

  it("renders plain items, not buttons, without onSelect", () => {
    renderStudio(<PipelineGraph nodes={NODES} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("flows data only from a finished stage into the running one", () => {
    const { container } = renderStudio(<PipelineGraph nodes={NODES} />);
    const beams = Array.from(container.querySelectorAll(".studio-pipeline-beam"));
    expect(beams.map((beam) => beam.getAttribute("data-state"))).toEqual([
      "flowing",
      "idle",
      "idle",
      "idle",
    ]);
    expect(container.querySelectorAll(".studio-flow")).toHaveLength(1);
  });

  it("puts a border beam on the running stage only", () => {
    const { container } = renderStudio(<PipelineGraph nodes={NODES} />);
    const beams = container.querySelectorAll(".studio-beam");
    expect(beams).toHaveLength(1);
    expect(beams[0]?.closest("li")?.getAttribute("data-stage")).toBe("method");
  });

  it("speaks Korean in the compact variant too", () => {
    renderStudio(<PipelineGraph nodes={NODES} size="compact" />, { locale: "ko" });
    const list = screen.getByRole("list", { name: "파이프라인 단계" });
    expect(within(list).getByText("문헌 조사: 승인됨")).toBeTruthy();
    expect(within(list).getByText("코딩: 검토 필요")).toBeTruthy();
  });

  it("stacks vertically when asked", () => {
    const { container } = renderStudio(<PipelineGraph nodes={NODES} orientation="vertical" />);
    expect(
      container.querySelector("[data-pipeline-axis]")?.getAttribute("data-pipeline-axis"),
    ).toBe("y");
  });

  it("freezes its loops while paused", () => {
    const { container, rerender } = renderStudio(<PipelineGraph nodes={NODES} paused />);
    const root = container.querySelector("[data-pipeline-axis]");
    expect(root?.getAttribute("data-paused")).toBe("true");
    rerender(<PipelineGraph nodes={NODES} />);
    expect(root?.hasAttribute("data-paused")).toBe(false);
  });
});

/** Elements in `item` (itself included) with an opacity utility: fading them fades their text. */
function faded(item: Element): string[] {
  return [item, ...Array.from(item.querySelectorAll("*"))]
    .map((element) => element.getAttribute("class") ?? "")
    .filter((className) => /(^|\s)opacity-\d/.test(className));
}

const STEPPED_BACK: PipelineNode[] = [
  { stage: "literature", status: "approved" },
  { stage: "method", status: "cancelled" },
  { stage: "coding", status: "invalidated" },
  { stage: "experiment", status: "skipped" },
  { stage: "writing", status: "skipped" },
];

describe("PipelineGraph stages that stepped back", () => {
  it.each(["large", "compact"] as const)(
    "never fade their text in the %s graph: dashed and neutral instead",
    (size) => {
      const { container } = renderStudio(<PipelineGraph nodes={STEPPED_BACK} size={size} />);
      for (const status of ["cancelled", "invalidated", "skipped"]) {
        for (const item of Array.from(container.querySelectorAll(`li[data-status="${status}"]`))) {
          expect(faded(item), status).toEqual([]);
          const node = item.firstElementChild;
          expect(node?.getAttribute("data-tone"), status).toBe("neutral");
          expect(node?.getAttribute("class"), status).toMatch(/(^|\s)border-dashed(\s|$)/);
        }
      }
      const approved = container.querySelector('li[data-status="approved"]')?.firstElementChild;
      expect(approved?.hasAttribute("data-tone")).toBe(false);
    },
  );

  it("show their status in full, in English and Korean", () => {
    renderStudio(<PipelineGraph nodes={STEPPED_BACK} />);
    expect(screen.getByText("Cancelled")).toBeTruthy();
    expect(screen.getByText("Outdated")).toBeTruthy();
    expect(screen.getAllByText("Not run")).toHaveLength(2);
    expect(screen.getByText("Coding: Outdated")).toBeTruthy();
    cleanup();
    renderStudio(<PipelineGraph nodes={STEPPED_BACK} />, { locale: "ko" });
    expect(screen.getByText("취소됨")).toBeTruthy();
    expect(screen.getAllByText("실행 안 함")).toHaveLength(2);
    expect(screen.getByText("방법론: 취소됨")).toBeTruthy();
  });
});

describe("PipelineGraph status pills", () => {
  it("wrap a long status instead of cutting it off, with the whole node as a tooltip", () => {
    const { container } = renderStudio(
      <PipelineGraph
        nodes={[
          { stage: "method", status: "changes_requested", attempts: 2 },
          { stage: "coding", status: "output_ready" },
        ]}
      />,
    );
    for (const status of ["Changes requested", "Needs review"]) {
      const label = screen.getByText(status);
      const pill = label.parentElement as HTMLElement;
      for (const element of [label, pill]) {
        expect(element.className, status).not.toMatch(/(^|\s)(truncate|whitespace-nowrap)(\s|$)/);
      }
    }
    const method = container.querySelector('li[data-status="changes_requested"]') as HTMLElement;
    expect(within(method).getByTitle("Method: Changes requested, Attempt 2")).toBeTruthy();
  });
});
