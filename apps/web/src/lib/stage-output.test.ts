import { describe, expect, it } from "vitest";
import type { ExperimentOutput, Stage } from "@/client";
import {
  countWords,
  findVersion,
  headlineMetric,
  isDemoOutput,
  isDemoReason,
  latestAttempt,
  latestOutput,
  latestVersion,
  outputAs,
  previousOutput,
  stageData,
  stageOverviews,
  stageVersions,
  summarizeOutput,
} from "./stage-output";
import {
  attemptOut,
  DEMO_CODING,
  DEMO_EXPERIMENT,
  DEMO_LITERATURE,
  DEMO_METHOD,
  DEMO_OUTPUTS,
  DEMO_WRITING,
  stageDetailOut,
  stageOutputOut,
  stageRunOut,
  versionOut,
} from "./stage-output.fixtures";
import { buildTimeline, STAGE_ORDER } from "./timeline";

const RUN_ID = "22222222-2222-4222-8222-222222222222";

describe("outputAs", () => {
  it("narrows every stage's demo output to its typed shape", () => {
    for (const stage of STAGE_ORDER) {
      const narrowed = outputAs(stage, stageOutputOut(DEMO_OUTPUTS[stage]));
      expect(narrowed.kind).toBe(stage);
      expect(narrowed.stage).toBe(stage);
      expect(narrowed.data).toBe(DEMO_OUTPUTS[stage]);
    }
  });

  it("gives typed data that a switch can use", () => {
    const narrowed = outputAs("literature", versionOut(DEMO_LITERATURE));
    if (narrowed.kind !== "literature") {
      throw new Error(`expected literature, got ${narrowed.kind}`);
    }
    expect(narrowed.data.papers[0]?.title).toContain("NYU Depth v2");
  });

  it("falls back to raw JSON when the API says the schema fails", () => {
    const narrowed = outputAs("method", versionOut(DEMO_METHOD, { schema_ok: false }));
    expect(narrowed).toEqual({
      kind: "raw",
      stage: "method",
      data: DEMO_METHOD,
      reason: "schema_failed",
    });
  });

  it("falls back to raw JSON for stages this client does not know", () => {
    expect(outputAs("review", stageOutputOut({ notes: "x" }))).toEqual({
      kind: "raw",
      stage: "review",
      data: { notes: "x" },
      reason: "unknown_stage",
    });
  });

  it("falls back to raw JSON for data without the stage's shape (Phase 1 placeholders)", () => {
    const placeholder = { summary: "<img src=x onerror=alert(1)>", papers: 2 };
    expect(outputAs("literature", stageOutputOut(placeholder))).toMatchObject({
      kind: "raw",
      reason: "unexpected_shape",
      data: placeholder,
    });
    // One wrong nested field is enough: views must never crash on it.
    const broken = {
      ...DEMO_LITERATURE,
      papers: [{ ...DEMO_LITERATURE.papers[0], authors: "Ada" }],
    };
    expect(outputAs("literature", stageOutputOut(broken)).kind).toBe("raw");
    const missing = { ...DEMO_EXPERIMENT, provenance: undefined };
    expect(outputAs("experiment", stageOutputOut(missing)).kind).toBe("raw");
  });

  it("accepts optional and nullable fields as the schemas allow them", () => {
    const { analyses: _analyses, ...withoutAnalyses } = DEMO_LITERATURE;
    expect(outputAs("literature", stageOutputOut(withoutAnalyses)).kind).toBe("literature");
    const paper = { ...DEMO_LITERATURE.papers[0], venue: null, doi: undefined };
    const papers = { ...DEMO_LITERATURE, papers: [paper] };
    expect(outputAs("literature", stageOutputOut(papers)).kind).toBe("literature");
    const unmeasured = { ...DEMO_EXPERIMENT, final_metrics: { abs_rel: null } };
    expect(outputAs("experiment", stageOutputOut(unmeasured)).kind).toBe("experiment");
  });

  it("returns null without an output", () => {
    expect(outputAs("method", null)).toBeNull();
    expect(outputAs("method", undefined)).toBeNull();
  });
});

describe("stageData", () => {
  it("returns the typed data, or null for another shape", () => {
    expect(stageData("coding", versionOut(DEMO_CODING))?.entrypoint).toBe("model.py:DepthNet");
    expect(stageData("coding", versionOut(DEMO_METHOD))).toBeNull();
    expect(stageData("writing", null)).toBeNull();
  });
});

describe("isDemoOutput", () => {
  it("knows the worker's demo reasons and the API's demo rule", () => {
    expect(
      isDemoOutput(versionOut(DEMO_LITERATURE, { degraded_reason: "literature.demo_search" })),
    ).toBe(true);
    expect(isDemoOutput(stageOutputOut(DEMO_METHOD, { degraded_reason: "stage.demo" }))).toBe(true);
    // agentic_api.demo.is_demo_reason: any dotted part "demo" or "demo_…".
    expect(isDemoReason("coding.demo_files")).toBe(true);
    expect(isDemoReason("demo")).toBe(true);
  });

  it("does not badge real or merely degraded outputs", () => {
    expect(
      isDemoOutput(stageOutputOut(DEMO_METHOD, { degraded_reason: "stage.placeholder" })),
    ).toBe(false);
    expect(
      isDemoOutput(stageOutputOut(DEMO_METHOD, { degraded: false, degraded_reason: null })),
    ).toBe(false);
    expect(isDemoReason("literature.search_pending")).toBe(false);
    expect(isDemoReason("stage.demonstration")).toBe(false);
    expect(isDemoOutput(null)).toBe(false);
  });
});

describe("versions and attempts", () => {
  // Attempt 1 was sent back; attempt 2 failed before any output; attempt 3 has an original
  // version and the reviewer's edit (version 2). The API lists oldest first; shuffle anyway.
  const sentBack = versionOut(DEMO_METHOD, {
    approval: {
      decision: "request_changes",
      comment: "Cite the 2024 papers",
      actor_id: "alice",
      actor_name: "Alice",
      at: "2026-10-30T01:30:00Z",
    },
  });
  const original = versionOut(DEMO_METHOD);
  const edited = versionOut(
    { ...DEMO_METHOD, implementation_focus: "A smaller student." },
    { version: 2, edited_by: "bob", edited_by_name: "Bob" },
  );
  const first = attemptOut(1, [sentBack], { status: "changes_requested" });
  const failed = attemptOut(2, [], { status: "failed", error: "stage.error" });
  const third = attemptOut(3, [edited, original], { feedback: "Cite the 2024 papers" });
  const detail = stageDetailOut(RUN_ID, "method", [third, first, failed]);

  it("orders versions oldest first and finds the newest", () => {
    expect(stageVersions(detail).map((ref) => [ref.attempt.attempt, ref.output.version])).toEqual([
      [1, 1],
      [3, 1],
      [3, 2],
    ]);
    expect(latestAttempt(detail)).toBe(third);
    expect(latestOutput(detail)).toEqual({ attempt: third, output: edited });
    expect(latestVersion(third.outputs)).toBe(edited);
    expect(latestVersion([])).toBeUndefined();
  });

  it("skips a newest attempt that has no output yet", () => {
    const running = attemptOut(4, [], { status: "running" });
    const withRunning = stageDetailOut(RUN_ID, "method", [first, third, running]);
    expect(latestAttempt(withRunning)).toBe(running);
    expect(latestOutput(withRunning)?.output).toBe(edited);
  });

  it("finds a version by id", () => {
    expect(findVersion(detail, original.id)).toEqual({ attempt: third, output: original });
    expect(findVersion(detail, "missing")).toBeUndefined();
    expect(findVersion(detail, null)).toBeUndefined();
    expect(findVersion(undefined, original.id)).toBeUndefined();
  });

  it("diffs an edit against the version before it", () => {
    expect(previousOutput(detail, edited.id)).toEqual({
      attempt: third,
      output: original,
      relation: "version",
    });
  });

  it("diffs a new attempt against the closest earlier attempt with an output", () => {
    expect(previousOutput(detail, original.id)).toEqual({
      attempt: first,
      output: sentBack,
      relation: "attempt",
    });
  });

  it("has nothing to diff the first output with", () => {
    expect(previousOutput(detail, sentBack.id)).toBeUndefined();
    expect(previousOutput(detail, "missing")).toBeUndefined();
    expect(latestOutput(stageDetailOut(RUN_ID, "writing", []))).toBeUndefined();
  });
});

describe("summaries", () => {
  it("counts the screened papers", () => {
    expect(summarizeOutput("literature", versionOut(DEMO_LITERATURE))).toEqual({
      kind: "literature",
      papersTotal: 5,
      papersIncluded: 3,
      papersMaybe: 1,
      papersExcluded: 1,
      analyses: 3,
    });
  });

  it("counts proposals and names the recommended one", () => {
    expect(summarizeOutput("method", versionOut(DEMO_METHOD))).toEqual({
      kind: "method",
      proposals: 3,
      recommended: "Scale-aware distillation from a frozen foundation teacher",
    });
  });

  it("counts files and lines, and reports the smoke test", () => {
    // The fixture keeps the first 6 lines of each of the 5 files.
    expect(summarizeOutput("coding", versionOut(DEMO_CODING))).toEqual({
      kind: "coding",
      files: 5,
      lines: 30,
      smokeTestPassed: true,
      entrypoint: "model.py:DepthNet",
    });
  });

  it("reports the experiment's headline metric (the one the draft reports first)", () => {
    expect(summarizeOutput("experiment", versionOut(DEMO_EXPERIMENT))).toEqual({
      kind: "experiment",
      status: "succeeded",
      epochs: 24,
      headline: { name: "abs_rel", split: "val", higherIsBetter: false, value: 0.1569 },
    });
  });

  it("counts the draft's words, sections and citations", () => {
    const summary = summarizeOutput("writing", versionOut(DEMO_WRITING));
    expect(summary).toMatchObject({
      kind: "writing",
      title: DEMO_WRITING.title,
      sections: 8,
      citations: 3,
    });
    expect(summary?.kind === "writing" && summary.words).toBe(countWords(DEMO_WRITING.markdown));
    expect(summary?.kind === "writing" && summary.words).toBeGreaterThan(150);
  });

  it("summarizes untyped data as raw, and no output as nothing", () => {
    expect(summarizeOutput("literature", stageOutputOut({ summary: "placeholder" }))).toEqual({
      kind: "raw",
      stage: "literature",
      reason: "unexpected_shape",
    });
    expect(summarizeOutput("literature", null)).toBeNull();
  });
});

describe("headlineMetric", () => {
  const experiment = (patch: Partial<ExperimentOutput>): ExperimentOutput => ({
    ...DEMO_EXPERIMENT,
    ...patch,
  });

  it("keeps an unmeasured final value as null, never 0", () => {
    const unmeasured = experiment({
      final_metrics: { ...DEMO_EXPERIMENT.final_metrics, abs_rel: null },
    });
    expect(headlineMetric(unmeasured)?.value).toBeNull();
  });

  it("uses the last epoch when final_metrics lacks the metric", () => {
    const series = DEMO_EXPERIMENT.series.find((item) => item.name === "abs_rel");
    const last = series?.points.at(-1)?.value;
    expect(headlineMetric(experiment({ final_metrics: {} }))?.value).toBe(last);
  });

  it("falls back to the validation loss, then to nothing", () => {
    const lossOnly = experiment({
      series: DEMO_EXPERIMENT.series.filter((s) => s.name === "loss"),
    });
    expect(headlineMetric(lossOnly)).toEqual({
      name: "val_loss",
      split: "val",
      higherIsBetter: false,
      value: 0.5401,
    });
    expect(headlineMetric(experiment({ series: [], final_metrics: {} }))).toBeNull();
  });
});

describe("countWords", () => {
  it("counts words, not Markdown punctuation", () => {
    expect(countWords("# Title\n\nDepth estimation **works** well.")).toBe(5);
    expect(countWords("")).toBe(0);
    expect(countWords("| AbsRel | 0.157 |\n|---|---|")).toBe(2);
  });

  it("does not count citation markers or link targets", () => {
    expect(countWords("Prior work [1], [2, 3] and [4–6] agrees.")).toBe(4);
    expect(countWords("See [the benchmark](https://example.org/nyu-depth-v2).")).toBe(3);
  });

  it("counts Korean words too", () => {
    expect(countWords("단안 깊이 추정은 어렵다.")).toBe(4);
  });
});

describe("stageOverviews", () => {
  it("adds each stage's newest output, summary and demo flag to the timeline", () => {
    const literature = stageRunOut("literature", "approved", {
      outputs: [
        stageOutputOut({ summary: "placeholder" }, { degraded_reason: "stage.placeholder" }),
        stageOutputOut(DEMO_LITERATURE, { version: 2, degraded_reason: "literature.demo_search" }),
      ],
    });
    const method = stageRunOut("method", "running");
    const entries = stageOverviews(buildTimeline(STAGE_ORDER, [literature, method], "running"));
    expect(entries.map((entry) => entry.stage)).toEqual([...STAGE_ORDER]);
    expect(entries[0]).toMatchObject({
      status: "approved",
      demo: true,
      summary: { kind: "literature", papersIncluded: 3, papersTotal: 5 },
    });
    expect(entries[0]?.output?.version).toBe(2);
    expect(entries[1]).toMatchObject({ status: "running", current: true, summary: null });
    expect(entries[1]?.output).toBeUndefined();
    expect(entries[4]).toMatchObject({ status: "pending", summary: null, demo: false });
  });

  it("keeps the stage types in step with the pipeline order", () => {
    const stages: readonly Stage[] = STAGE_ORDER;
    expect(Object.keys(DEMO_OUTPUTS).sort()).toEqual([...stages].sort());
  });
});
