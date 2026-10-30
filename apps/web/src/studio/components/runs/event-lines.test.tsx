// @vitest-environment jsdom
import { cleanup, renderHook } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { runEvent } from "@/hooks/run-hooks.fixtures";
import type { Locale } from "@/i18n/config";
import { enMessages, koMessages } from "@/test/messages";
import { useEventDescriber } from "./event-lines";

afterEach(cleanup);

function describer(locale: Locale = "en") {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <NextIntlClientProvider
      locale={locale}
      messages={locale === "ko" ? koMessages : enMessages}
      timeZone="Asia/Seoul"
    >
      {children}
    </NextIntlClientProvider>
  );
  return renderHook(() => useEventDescriber(), { wrapper }).result.current;
}

const progress = (stage: string, code: string, params: Record<string, unknown>, message = "") =>
  runEvent("log", { stage, code, params, message });

describe("useEventDescriber", () => {
  it("translates every demo progress code", () => {
    const toLine = describer();
    const lines = [
      progress("literature", "demo.screen", { candidates: 32, papers: 5 }),
      progress("literature", "demo.analyse", { papers: 3 }),
      progress("literature", "demo.synthesise", { findings: 1 }),
      progress("method", "demo.gaps", { gaps: 4 }),
      progress("method", "demo.propose", { proposals: 3 }),
      progress("method", "demo.recommend", { option: "Distillation" }),
      progress("coding", "demo.code", { files: 5, entrypoint: "model.py:DepthNet" }),
      progress("coding", "demo.test", { tests: 4 }),
      progress("coding", "demo.smoke_test", { passed: true, seconds: 31.3 }),
      progress("coding", "demo.smoke_test", { passed: false, seconds: 2 }),
      progress("experiment", "demo.train", { epochs: 24, dataset: "nyu2", gpu: "GTX 1060" }),
      progress("experiment", "demo.train", { epochs: 1, dataset: "nyu2", gpu: null }),
      progress("experiment", "demo.epoch", {
        epoch: 6,
        epochs: 24,
        metric: "abs_rel",
        value: 0.299,
      }),
      progress("experiment", "demo.epoch", { epoch: 12, epochs: 24, metric: "rmse", value: null }),
      progress("writing", "demo.outline", { sections: 8 }),
      progress("writing", "demo.draft", { section: "Method", index: 4, sections: 8 }),
      progress("writing", "demo.cite", { citations: 3 }),
    ].map((event) => toLine(event));
    expect(lines.map((line) => line.text)).toEqual([
      "Screening 32 candidates; keeping the 5 most relevant papers",
      "Reading 3 included papers in full",
      "Writing the synthesis from 1 key finding",
      "Mapping 4 research gaps",
      "Drafting 3 proposals",
      "Recommending: Distillation",
      "Writing 5 files (entry point model.py:DepthNet)",
      "Running 4 unit tests and a 2-batch dry run",
      "Smoke test passed in 31.3 s",
      "Smoke test failed after 2 s",
      "Training for 24 epochs on nyu2 (GTX 1060)",
      "Training for 1 epoch on nyu2",
      "Epoch 6/24: validation abs_rel 0.299",
      "Epoch 12/24: validation rmse not measured",
      "Outlining 8 sections",
      "Drafting Method (4/8)",
      "Linking 3 citations to the included papers",
    ]);
    expect(lines.every((line) => line.kind === "progress" && line.group === "stages")).toBe(true);
    expect(lines[0]?.stage).toBe("literature");
  });

  it("speaks Korean, with the paper sources in the UI language", () => {
    const toLine = describer("ko");
    const search = toLine(
      progress("literature", "demo.search", { sources: ["arxiv", "openalex"], queries: 4 }),
    );
    const sources = new Intl.ListFormat("ko", { type: "conjunction" }).format([
      "arXiv",
      "OpenAlex",
    ]);
    expect(search.text).toBe(`${sources}에서 검색어 4개로 검색하는 중`);
    expect(
      toLine(progress("experiment", "demo.epoch", { epoch: 6, epochs: 24, metric: "rmse" })).text,
    ).toBe("에포크 6/24: 검증 rmse 측정되지 않음");
    const call = toLine(runEvent("llm.call", { model: "m", tier: "free", cost_usd: "0" }));
    expect(call).toMatchObject({ text: "LLM 호출 · m (무료)", detail: null, group: "llm" });
    expect(
      toLine(runEvent("run.retried", { stage: "method", requested_stage: "method" })).text,
    ).toBe("방법론부터 실행을 다시 시작함");
  });

  it("words a finished epoch by its headline metric, never as raw JSON", () => {
    const toLine = describer();
    const epoch = runEvent("experiment.epoch", {
      stage: "experiment",
      job_id: "job-1",
      kind: "train",
      ordinal: 1,
      epoch: 2,
      train: { loss: 0.31, rmse: 0.4981, mae: 0.35, abs_rel: 0.11 },
      val: { loss: 0.43, rmse: 0.512, mae: 0.38, abs_rel: 0.12 },
    });
    expect(toLine(epoch)).toEqual({
      kind: "epoch",
      tone: "info",
      stage: "experiment",
      text: "Epoch 2: val RMSE 0.512",
      detail: "train 0.4981",
      group: "stages",
    });
    const smoke = runEvent("experiment.epoch", {
      stage: "coding",
      job_id: "smoke-2",
      kind: "smoke",
      ordinal: 2,
      epoch: 0,
      val: { loss: 2.5, rmse: null },
      train: {},
    });
    expect(toLine(smoke)).toMatchObject({
      stage: "coding",
      text: "Smoke test 2, epoch 0: val loss 2.5",
      detail: null,
    });
    expect(describer("ko")(epoch)).toMatchObject({
      text: "에포크 2: 검증 RMSE 0.512",
      detail: "학습 0.4981",
    });
    expect(toLine(runEvent("experiment.epoch", { stage: "experiment" }))).toMatchObject({
      kind: "raw",
      text: 'experiment.epoch {"stage":"experiment"}',
    });
  });

  it("translates the GPU stages' progress in both languages", () => {
    const lines = [
      progress("coding", "coding.written", { try: 1, files: 2, lines: 87 }),
      progress("coding", "gpu.started", { kind: "smoke", ordinal: 1 }),
      progress("coding", "coding.smoke_passed", { try: 1, seconds: 16.04 }),
      progress("experiment", "gpu.queue_full", { kind: "train", limit: 2 }),
      progress("experiment", "experiment.finished", { status: "timeout", epochs: 2 }),
    ];
    expect(lines.map((event) => describer()(event).text)).toEqual([
      "Try 1: wrote 2 files (87 lines)",
      "Smoke test 1 running on the GPU",
      "Try 1: the smoke test passed in 16 s",
      "Training waits: you already have 2 GPU jobs queued, the most allowed",
      "Training stopped at its time limit after 2 epochs",
    ]);
    expect(lines.map((event) => describer("ko")(event).text)).toEqual([
      "1번째 시도: 파일 2개를 작성했습니다(87줄)",
      "스모크 테스트 1: GPU에서 실행 중",
      "1번째 시도: 스모크 테스트 통과(16초)",
      "학습 대기 중: 대기열에 올린 GPU 작업이 이미 최대치(2개)입니다",
      "학습 시간 한도 도달: 2에포크 후 중단",
    ]);
    expect(describer()(lines[0] as ReturnType<typeof runEvent>)).toMatchObject({
      kind: "progress",
      stage: "coding",
    });
  });

  it("falls back to the English message for unknown codes and malformed params", () => {
    const toLine = describer("ko");
    expect(
      toLine(progress("literature", "demo.search", { queries: "four" }, "Searching arXiv")).text,
    ).toBe("Searching arXiv");
    expect(toLine(progress("method", "demo.future", {}, "Thinking")).text).toBe("Thinking");
  });

  it("says why a stage waits and when it tries again, in the app's time zone", () => {
    const waiting = runEvent("stage.waiting", {
      stage: "literature",
      attempt: 1,
      reason: "call.in_progress",
      retry_at: "2026-10-30T05:30:00Z",
    });
    const line = describer()(waiting);
    expect(line).toMatchObject({
      kind: "waiting",
      tone: "warning",
      stage: "literature",
      text: "Literature is waiting: A model call from an earlier try is still in progress.",
    });
    expect(line.detail).toMatch(/^It tries again by itself at Oct 30, 2:30\sPM\.$/);
    expect(describer("ko")(waiting)).toMatchObject({
      text: "문헌 조사 단계 대기 중: 이전 시도의 모델 호출이 아직 끝나지 않았습니다.",
      detail: "10월 30일 오후 2:30에 자동으로 다시 시도합니다.",
    });
    expect(
      describer()(runEvent("stage.waiting", { stage: "method", reason: "quota.new_kind" })),
    ).toMatchObject({
      text: "Method is waiting: It waits a moment before it tries again.",
      detail: null,
    });
  });

  it("explains retries, outdated stages and decisions", () => {
    const toLine = describer();
    expect(
      toLine(runEvent("stage.invalidated", { stage: "coding", attempt: 2, retry_stage: "method" })),
    ).toMatchObject({
      kind: "invalidated",
      stage: "coding",
      text: "Coding: attempt 2 is outdated after the retry from Method",
    });
    expect(
      toLine(runEvent("run.retried", { stage: "literature", requested_stage: "method" })).text,
    ).toBe(
      "Run restarted from Literature: Method was asked for, but an earlier stage had no approved output",
    );
    expect(
      toLine(
        runEvent("stage.decided", {
          stage: "method",
          decision: "approve",
          automatic: true,
          edited: true,
          comment: "Fine",
        }),
      ),
    ).toMatchObject({
      tone: "success",
      text: "Method: Approved · automatically · with edits",
      detail: "“Fine”",
    });
    expect(
      toLine(
        runEvent("llm.call", {
          stage: "writing",
          model: "openai/gpt-4o",
          tier: "paid",
          cost_usd: "0.0125",
          switched_to_free: true,
        }),
      ),
    ).toMatchObject({
      text: "LLM call · openai/gpt-4o (paid)",
      detail: "$0.0125 · switched to free models",
      tone: "warning",
    });
  });
});
