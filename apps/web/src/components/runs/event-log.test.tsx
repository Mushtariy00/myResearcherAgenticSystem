// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithIntl } from "@/components/shared/test-utils";
import type { RunEvent } from "@/lib/run-events";
import { EventLog } from "./event-log";

afterEach(cleanup);

let seq = 0;
function event(type: string, payload: Record<string, unknown>): RunEvent {
  seq += 1;
  return { seq, type, payload, created_at: "2026-10-30T01:00:00+00:00" };
}

/** The type label and the summary of each line of the log. */
function lines(): string[][] {
  const log = screen.getByRole("log", { name: "Live events" });
  return within(log)
    .getAllByRole("listitem")
    .map((item) => [...item.children].slice(1).map((cell) => cell.textContent ?? ""));
}

describe("EventLog", () => {
  it("translates retries, outdated outputs, demo progress and LLM calls", () => {
    renderWithIntl(
      <EventLog
        state="live"
        onReconnect={vi.fn()}
        events={[
          event("stage.invalidated", {
            stage: "method",
            attempt: 1,
            stage_run_id: "x",
            retry_stage: "literature",
          }),
          event("run.retried", {
            stage: "literature",
            requested_stage: "method",
            execution_id: "e1",
          }),
          event("log", {
            stage: "literature",
            code: "demo.search",
            params: { sources: ["arxiv", "openalex"], queries: 4 },
            message: "Searching arXiv, OpenAlex with 4 queries",
          }),
          event("log", {
            stage: "experiment",
            code: "demo.epoch",
            params: { epoch: 24, epochs: 24, metric: "abs_rel", value: null },
            message: "Epoch 24/24: val abs_rel not measured",
          }),
          event("log", {
            stage: "coding",
            code: "demo.smoke_test",
            params: { passed: true, seconds: 31.3 },
            message: "Smoke test passed in 31 s",
          }),
          // An unknown code, and a known one with params it cannot use: the English message.
          event("log", {
            stage: "writing",
            code: "demo.new_step",
            params: {},
            message: "New step",
          }),
          event("log", { code: "demo.gaps", params: { gaps: "four" }, message: "Mapping gaps" }),
          event("llm.call", {
            stage: "method",
            model: "openai/gpt-5-mini",
            tier: "paid",
            cost_usd: "0.0125",
            switched_to_free: false,
            replayed: false,
          }),
          event("custom.thing", { a: 1 }),
        ]}
      />,
    );
    expect(lines()).toEqual([
      [
        "Outdated",
        "The Method output of attempt 1 is outdated: the run starts again at Literature",
      ],
      [
        "Retry",
        "Retrying from Literature: Method was asked for, but an earlier stage had no approved output",
      ],
      ["Progress", "Literature: Searching arXiv and OpenAlex with 4 queries"],
      ["Progress", "Experiment: Epoch 24/24: validation abs_rel not measured"],
      ["Progress", "Coding: Smoke test passed in 31.3 s"],
      ["Progress", "Writing: New step"],
      ["Progress", "Mapping gaps"],
      ["LLM call", "Method: LLM call · openai/gpt-5-mini (paid) · $0.0125"],
      ["custom.thing", '{"a":1}'],
    ]);
  });

  it("says why a stage waits and when it tries again", () => {
    renderWithIntl(
      <EventLog
        state="live"
        onReconnect={vi.fn()}
        events={[
          event("stage.waiting", {
            stage: "coding",
            attempt: 2,
            reason: "lab_balance.exhausted",
            retry_at: "2026-10-30T01:15:00Z",
          }),
        ]}
      />,
    );
    const [line] = lines();
    expect(line?.[0]).toBe("Waiting");
    expect(line?.[1]).toMatch(
      /^Coding is waiting: The lab's OpenRouter balance is used up\. The run continues after a top-up\. It tries again by itself at Oct 30, 10:15\sAM\.$/,
    );
  });

  it("speaks Korean too", () => {
    renderWithIntl(
      <EventLog
        state="ended"
        onReconnect={vi.fn()}
        events={[
          event("run.retried", { stage: "coding", requested_stage: "coding" }),
          event("log", {
            stage: "literature",
            code: "demo.analyse",
            params: { papers: 3 },
            message: "Analysing 3 included papers",
          }),
        ]}
      />,
      { locale: "ko" },
    );
    const log = screen.getByRole("log", { name: "실시간 이벤트" });
    expect(log.textContent).toContain("코딩부터 재시도");
    expect(log.textContent).toContain("문헌 조사: 포함된 논문 3편을 분석하는 중");
  });
});
