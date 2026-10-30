// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import type { Locale } from "@/i18n/config";
import { type EpochRecord, epochRecord } from "@/lib/run-events";
import { JOB_ERROR_CODES, useEpochLine, useStageLogLine } from "./stage-log";
import { renderWithIntl } from "./test-utils";

function Line({ code, params }: { code: string; params: Record<string, unknown> }) {
  const line = useStageLogLine()(code, params);
  return <p>{line ?? "(fallback)"}</p>;
}

function lineOf(code: string, params: Record<string, unknown>, locale: Locale = "en"): string {
  const { container, unmount } = renderWithIntl(<Line code={code} params={params} />, { locale });
  const text = container.textContent ?? "";
  unmount();
  return text;
}

function Epoch({ record }: { record: EpochRecord }) {
  const line = useEpochLine()(record);
  return (
    <>
      <p>{line.text}</p>
      <p>{line.detail ?? "(no detail)"}</p>
    </>
  );
}

/** An experiment.epoch event's line and detail. */
function epochOf(payload: Record<string, unknown>, locale: Locale = "en"): [string, string] {
  const record = epochRecord(payload);
  if (!record) {
    throw new Error("not an epoch");
  }
  const { container, unmount } = renderWithIntl(<Epoch record={record} />, { locale });
  const [text, detail] = [...container.querySelectorAll("p")].map((p) => p.textContent ?? "");
  unmount();
  return [text ?? "", detail ?? ""];
}

describe("useStageLogLine", () => {
  it("words each step of the real literature stage", () => {
    expect(
      lineOf("literature.searched", {
        queries: 6,
        sources: ["openalex", "arxiv"],
        found: 215,
        incomplete: 5,
      }),
    ).toBe(
      "Searched OpenAlex and arXiv with 6 queries: 215 papers found, 5 of them left out for lack " +
        "of authors, a year or an abstract",
    );
    expect(lineOf("literature.searched", { queries: 1, sources: ["arxiv"], found: 1 })).toBe(
      "Searched arXiv with 1 query: 1 paper found",
    );
    expect(
      lineOf("literature.source_failed", {
        source: "semantic_scholar",
        error: "source.rate_limited",
      }),
    ).toBe(
      "Semantic Scholar could not be searched (it is limiting requests); continuing without it",
    );
    expect(lineOf("literature.screened", { candidates: 15, included: 4 })).toBe(
      "Screened 15 candidates and included 4 papers for full reading",
    );
    expect(lineOf("literature.fetched", { pdfs: 3, abstract_only: 1 })).toBe(
      "Fetched 3 open-access PDFs; 1 paper has only an abstract",
    );
    expect(lineOf("literature.fetched", { pdfs: 4, abstract_only: 0 })).toBe(
      "Fetched 4 open-access PDFs: every included paper has its full text",
    );
    expect(lineOf("literature.parsed", { papers: 4 })).toBe("Extracted the full text of 4 papers");
    expect(lineOf("literature.analyzed", { papers: 1 })).toBe("Analysed 1 paper");
    expect(lineOf("literature.synthesized", { findings: 4 })).toBe(
      "Wrote the synthesis from 4 key findings",
    );
  });

  it("words the method and writing stages", () => {
    expect(lineOf("method.proposed", { proposals: 3, gaps: 2 })).toBe(
      "Proposed 3 methods for 2 research gaps",
    );
    expect(lineOf("writing.outlined", { sections: 6 })).toBe("Outlined 6 sections");
    expect(lineOf("writing.drafted", { section: "Related work", index: 2, sections: 6 })).toBe(
      "Drafted Related work (2/6)",
    );
    expect(lineOf("writing.cited", { citations: 1, removed: 0 })).toBe("Cited 1 paper");
    expect(lineOf("writing.cited", { citations: 9, removed: 2 })).toBe(
      "Cited 9 papers; removed 2 citations of papers that are not in the review",
    );
  });

  it("reads the same lines in Korean", () => {
    expect(lineOf("literature.screened", { candidates: 15, included: 4 }, "ko")).toBe(
      "후보 15편을 선별해 4편을 정독 대상으로 포함했습니다",
    );
    expect(
      lineOf(
        "literature.source_failed",
        { source: "openalex", error: "source.quota_exhausted" },
        "ko",
      ),
    ).toBe("OpenAlex에서 검색하지 못해(일일 한도 소진) 이 출처 없이 계속합니다");
    expect(lineOf("method.proposed", { proposals: 3, gaps: 2 }, "ko")).toBe(
      "연구 공백 2개에 대해 방법 3개를 제안했습니다",
    );
  });

  it("words the GPU queue of the coding and experiment stages", () => {
    expect(lineOf("gpu.queue_full", { kind: "train", limit: 2 })).toBe(
      "Training waits: you already have 2 GPU jobs queued, the most allowed",
    );
    expect(lineOf("gpu.queue_full", { kind: "smoke", limit: 2 })).toBe(
      "The smoke test waits: you already have 2 GPU jobs queued, the most allowed",
    );
    expect(lineOf("gpu.queued", { kind: "smoke", ordinal: 2 })).toBe(
      "Smoke test 2 queued for the GPU",
    );
    expect(lineOf("gpu.started", { kind: "train", ordinal: 1 })).toBe(
      "Training running on the GPU",
    );
    expect(lineOf("gpu.executor_down", {})).toBe(
      "The GPU executor is not running; the job waits for it",
    );
  });

  it("words each try of the coding stage, with the reason a smoke test failed", () => {
    expect(lineOf("coding.written", { try: 1, files: 2, lines: 87 })).toBe(
      "Try 1: wrote 2 files (87 lines)",
    );
    expect(lineOf("coding.written", { try: 2, files: 1, lines: 1 })).toBe(
      "Try 2: wrote 1 file (1 line)",
    );
    expect(lineOf("coding.refused", { try: 1, findings: 1 })).toBe(
      "Try 1: the checks refused the code (1 finding), so it did not run",
    );
    expect(lineOf("coding.smoke_failed", { try: 1, error_code: "code.shape_mismatch" })).toBe(
      "Try 1: the smoke test failed: the model's output has the wrong shape",
    );
    expect(lineOf("coding.smoke_failed", { try: 3, error_code: "job.timeout" })).toBe(
      "Try 3: the smoke test failed: it ran out of time",
    );
    // A code this interface does not know yet is named; anything else is not shown.
    expect(lineOf("coding.smoke_failed", { try: 1, error_code: "train.new_kind" })).toBe(
      "Try 1: the smoke test failed: an unexpected error (train.new_kind)",
    );
    expect(lineOf("coding.smoke_passed", { try: 2, seconds: 13.3 })).toBe(
      "Try 2: the smoke test passed in 13.3 s",
    );
  });

  it("has words for every reason a GPU job can fail", () => {
    for (const code of JOB_ERROR_CODES) {
      const line = lineOf("coding.smoke_failed", { try: 1, error_code: code });
      expect(line, code).toMatch(/^Try 1: the smoke test failed: [a-z]/);
      expect(line, code).not.toContain(code);
      expect(lineOf("coding.smoke_failed", { try: 1, error_code: code }, "ko"), code).not.toContain(
        code,
      );
    }
  });

  it("words the experiment's plan and how its training ended", () => {
    expect(lineOf("experiment.planned", { epochs: 3, steps: 1000, batch_size: 8 })).toBe(
      "Training plan: 3 epochs of up to 1,000 steps at batch size 8",
    );
    expect(lineOf("experiment.finished", { status: "succeeded", epochs: 3 })).toBe(
      "Training succeeded: 3 epochs completed",
    );
    expect(lineOf("experiment.finished", { status: "failed", epochs: 0 })).toBe(
      "Training failed after 0 epochs",
    );
    expect(lineOf("experiment.finished", { status: "timeout", epochs: 1 })).toBe(
      "Training stopped at its time limit after 1 epoch",
    );
    expect(lineOf("experiment.finished", { status: "cancelled", epochs: 2 })).toBe(
      "Training was cancelled after 2 epochs",
    );
  });

  it("reads the GPU stages' lines in Korean", () => {
    expect(lineOf("gpu.queued", { kind: "smoke", ordinal: 1 }, "ko")).toBe(
      "스모크 테스트 1: GPU 대기열에 올렸습니다",
    );
    expect(lineOf("coding.smoke_failed", { try: 2, error_code: "train.oom" }, "ko")).toBe(
      "2번째 시도: 스모크 테스트 실패: GPU 메모리 부족",
    );
    expect(lineOf("experiment.planned", { epochs: 3, steps: 1000, batch_size: 8 }, "ko")).toBe(
      "학습 계획: 3에포크, 에포크당 최대 1,000스텝, 배치 크기 8",
    );
    expect(lineOf("experiment.finished", { status: "succeeded", epochs: 3 }, "ko")).toBe(
      "학습 성공: 3에포크 완료",
    );
  });

  it("leaves the GPU stages' malformed params to the worker's English message", () => {
    expect(lineOf("gpu.queue_full", { kind: "eval", limit: 2 })).toBe("(fallback)");
    expect(lineOf("gpu.queued", { kind: "smoke", ordinal: 0 })).toBe("(fallback)");
    expect(lineOf("coding.written", { try: 0, files: 2, lines: 87 })).toBe("(fallback)");
    expect(lineOf("coding.smoke_failed", { try: 1, error_code: "<b>boom</b>" })).toBe("(fallback)");
    expect(lineOf("coding.smoke_passed", { try: 1, seconds: -1 })).toBe("(fallback)");
    expect(lineOf("experiment.planned", { epochs: 3, steps: "1000", batch_size: 8 })).toBe(
      "(fallback)",
    );
    expect(lineOf("experiment.finished", { status: "exploded", epochs: 3 })).toBe("(fallback)");
  });

  it("words an epoch by its headline metric, with the training value as detail", () => {
    const epoch = {
      stage: "experiment",
      job_id: "job-1",
      kind: "train",
      ordinal: 1,
      epoch: 2,
      train: { loss: 0.31, rmse: 0.4981, mae: 0.35, abs_rel: 0.11 },
      val: { loss: 0.43, rmse: 0.512, mae: 0.38, abs_rel: 0.12 },
    };
    expect(epochOf(epoch)).toEqual(["Epoch 2: val RMSE 0.512", "train 0.4981"]);
    expect(epochOf(epoch, "ko")).toEqual(["에포크 2: 검증 RMSE 0.512", "학습 0.4981"]);
    expect(
      epochOf({ ...epoch, kind: "smoke", ordinal: 2, epoch: 0, val: { rmse: 3.21456 }, train: {} }),
    ).toEqual(["Smoke test 2, epoch 0: val RMSE 3.215", "(no detail)"]);
  });

  it("says a metric was not measured, never 0", () => {
    const base = { kind: "train", job_id: "j", epoch: 1 };
    expect(epochOf({ ...base, val: { rmse: null }, train: { rmse: null } })).toEqual([
      "Epoch 1: val RMSE not measured",
      "(no detail)",
    ]);
    expect(epochOf({ ...base, val: { loss: 0.43 } }, "ko")[0]).toBe("에포크 1: 검증 손실 0.43");
    expect(epochOf({ ...base, val: {}, train: {} })[0]).toBe("Epoch 1: nothing measured");
  });

  it("leaves other codes and malformed params to the worker's English message", () => {
    expect(lineOf("demo.search", { queries: 3, sources: ["arxiv"] })).toBe("(fallback)");
    expect(lineOf("literature.screened", { candidates: "15", included: 4 })).toBe("(fallback)");
    expect(lineOf("literature.source_failed", { source: "arxiv", error: "boom" })).toBe(
      "(fallback)",
    );
    expect(lineOf("literature.parsed", { papers: -1 })).toBe("(fallback)");
    expect(lineOf("writing.drafted", { section: "", index: 1, sections: 2 })).toBe("(fallback)");
  });
});
