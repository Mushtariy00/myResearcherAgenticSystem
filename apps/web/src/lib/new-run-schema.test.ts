import { describe, expect, expectTypeOf, it } from "vitest";
import type { RunConfig, RunCreate, RunEstimateIn, Stage } from "@/client";
import {
  estimateBodyOf,
  firstStepWithError,
  isPipelinePrefix,
  lastStageOf,
  NEW_RUN_ERROR_CODES,
  NEW_RUN_STEPS,
  type NewRunFieldPath,
  type NewRunFormInput,
  NewRunValidationError,
  type NewRunValues,
  newRunDefaults,
  newRunErrorValues,
  newRunFieldError,
  newRunSchema,
  RUN_CONFIG_DEFAULTS,
  SEARCH_SOURCES,
  type SearchSource,
  serverFieldErrors,
  stagesThrough,
} from "./new-run-schema";
import { STAGE_ORDER } from "./timeline";

type ConfigInput = NewRunFormInput["config"];

function valid(overrides: Partial<Omit<NewRunFormInput, "config">> = {}): NewRunFormInput {
  return { ...newRunDefaults(), topic: "Monocular depth estimation", ...overrides };
}

function withConfig(config: Partial<ConfigInput>): NewRunFormInput {
  const values = valid();
  return { ...values, config: { ...values.config, ...config } };
}

/** The first error code at each path, the way react-hook-form shows them. */
function errors(values: unknown): Record<string, string> {
  const result = newRunSchema.safeParse(values);
  if (result.success) {
    return {};
  }
  const found: Record<string, string> = {};
  for (const issue of result.error.issues) {
    found[issue.path.join(".")] ??= issue.message;
  }
  return found;
}

describe("newRunSchema", () => {
  it("accepts the defaults with a topic and outputs a RunCreate body", () => {
    const result = newRunSchema.parse(valid({ topic: "  Monocular depth estimation  " }));
    expect(result).toEqual({
      topic: "Monocular depth estimation",
      llm_policy: "auto",
      budget_cap_usd: null,
      config: {
        year_from: 2018,
        year_to: 2026,
        sources: ["arxiv", "semantic_scholar", "openalex"],
        max_papers: 20,
        stages: ["literature", "method", "coding", "experiment", "writing"],
        dataset: "nyu2",
      },
    });
  });

  it("mirrors RunConfig's defaults", () => {
    expect(RUN_CONFIG_DEFAULTS).toEqual({
      year_from: 2018,
      year_to: 2026,
      sources: ["arxiv", "semantic_scholar", "openalex"],
      max_papers: 20,
      stages: [...STAGE_ORDER],
      dataset: "nyu2",
    });
  });

  it("checks the topic length after trimming, counting characters like Python", () => {
    expect(errors(valid({ topic: "  ab  " }))).toEqual({ topic: "topic.tooShort" });
    expect(errors(valid({ topic: "abc" }))).toEqual({});
    expect(errors(valid({ topic: "a".repeat(500) }))).toEqual({});
    expect(errors(valid({ topic: "a".repeat(501) }))).toEqual({ topic: "topic.tooLong" });
    // 499 letters and an emoji: 500 characters for the API, 501 UTF-16 units.
    expect(errors(valid({ topic: `${"a".repeat(499)}🧪` }))).toEqual({});
    expect(errors(valid({ topic: "깊이 추정" }))).toEqual({});
  });

  it("requires stages to be a prefix of the pipeline starting with literature", () => {
    for (const stages of [["literature"], ["literature", "method"], [...STAGE_ORDER]]) {
      expect(errors(withConfig({ stages })), stages.join()).toEqual({});
    }
    expect(errors(withConfig({ stages: [] }))).toEqual({ "config.stages": "stages.empty" });
    expect(errors(withConfig({ stages: ["method"] }))).toEqual({
      "config.stages": "stages.notPrefix",
    });
    expect(errors(withConfig({ stages: ["literature", "coding"] }))).toEqual({
      "config.stages": "stages.notPrefix",
    });
    expect(errors(withConfig({ stages: ["literature", "literature"] }))).toEqual({
      "config.stages": "stages.notPrefix",
    });
    expect(errors(withConfig({ stages: ["literature", "review"] }))).toEqual({
      "config.stages": "stages.invalid",
    });
  });

  it("keeps years within 1990..2100, whole, and in order", () => {
    expect(errors(withConfig({ year_from: 1990, year_to: 2100 }))).toEqual({});
    expect(errors(withConfig({ year_from: 2020, year_to: 2020 }))).toEqual({});
    expect(errors(withConfig({ year_from: 1989 }))).toEqual({
      "config.year_from": "year.outOfRange",
    });
    expect(errors(withConfig({ year_to: 2101 }))).toEqual({ "config.year_to": "year.outOfRange" });
    expect(errors(withConfig({ year_from: 2020.5 }))).toEqual({
      "config.year_from": "year.invalid",
    });
    expect(errors(withConfig({ year_from: "" }))).toEqual({ "config.year_from": "year.invalid" });
    expect(errors(withConfig({ year_from: null }))).toEqual({ "config.year_from": "year.invalid" });
    expect(errors(withConfig({ year_from: Number.NaN }))).toEqual({
      "config.year_from": "year.invalid",
    });
    expect(errors(withConfig({ year_from: 2025, year_to: 2020 }))).toEqual({
      "config.year_to": "year.order",
    });
  });

  it("reads years typed as text", () => {
    const parsed = newRunSchema.parse(withConfig({ year_from: " 2019 ", year_to: "2024" }));
    expect(parsed.config).toMatchObject({ year_from: 2019, year_to: 2024 });
  });

  it("reports the year order even while another option is invalid", () => {
    expect(errors(withConfig({ year_from: 2025, year_to: 2020, max_papers: 3 }))).toEqual({
      "config.year_to": "year.order",
      "config.max_papers": "maxPapers.outOfRange",
    });
  });

  it("does not compare years when one of them is invalid", () => {
    expect(errors(withConfig({ year_from: 2200, year_to: 2020 }))).toEqual({
      "config.year_from": "year.outOfRange",
    });
  });

  it("needs at least one source, each known and listed once", () => {
    expect(errors(withConfig({ sources: ["crossref"] }))).toEqual({});
    expect(errors(withConfig({ sources: [...SEARCH_SOURCES] }))).toEqual({});
    expect(errors(withConfig({ sources: [] }))).toEqual({ "config.sources": "sources.empty" });
    expect(errors(withConfig({ sources: ["arxiv", "arxiv"] }))).toEqual({
      "config.sources": "sources.duplicate",
    });
    expect(errors(withConfig({ sources: ["arxiv", "google_scholar"] }))).toEqual({
      "config.sources": "sources.invalid",
    });
  });

  it("keeps the number of papers within 5..50", () => {
    expect(errors(withConfig({ max_papers: 5 }))).toEqual({});
    expect(errors(withConfig({ max_papers: 50 }))).toEqual({});
    expect(errors(withConfig({ max_papers: 4 }))).toEqual({
      "config.max_papers": "maxPapers.outOfRange",
    });
    expect(errors(withConfig({ max_papers: 51 }))).toEqual({
      "config.max_papers": "maxPapers.outOfRange",
    });
    expect(errors(withConfig({ max_papers: 12.5 }))).toEqual({
      "config.max_papers": "maxPapers.invalid",
    });
  });

  it("treats an empty cost cap as no cap and keeps the typed decimal", () => {
    const cap = (budget_cap_usd: unknown) =>
      newRunSchema.safeParse(valid({ budget_cap_usd: budget_cap_usd as never }));
    for (const empty of ["", "   ", null, undefined, Number.NaN]) {
      expect(cap(empty).data?.budget_cap_usd, String(empty)).toBeNull();
    }
    expect(cap("0").data?.budget_cap_usd).toBe("0");
    expect(cap(" 12.50 ").data?.budget_cap_usd).toBe("12.50");
    expect(cap("1000").data?.budget_cap_usd).toBe("1000");
    expect(cap(2.5).data?.budget_cap_usd).toBe("2.5");
  });

  it("rejects negative, too high and malformed cost caps", () => {
    expect(errors(valid({ budget_cap_usd: "-1" }))).toEqual({ budget_cap_usd: "budget.negative" });
    expect(errors(valid({ budget_cap_usd: -0.01 }))).toEqual({
      budget_cap_usd: "budget.negative",
    });
    expect(errors(valid({ budget_cap_usd: "1000.01" }))).toEqual({
      budget_cap_usd: "budget.tooHigh",
    });
    for (const text of ["abc", "1e3", "1,5", "Infinity", ".5"]) {
      expect(errors(valid({ budget_cap_usd: text })), text).toEqual({
        budget_cap_usd: "budget.invalid",
      });
    }
    expect(errors(valid({ budget_cap_usd: Number.POSITIVE_INFINITY }))).toEqual({
      budget_cap_usd: "budget.invalid",
    });
  });

  it("knows only the auto and free policies", () => {
    expect(errors(valid({ llm_policy: "free" }))).toEqual({});
    expect(errors(valid({ llm_policy: "paid" as never }))).toEqual({
      llm_policy: "llmPolicy.invalid",
    });
  });

  it("reads an empty dataset choice as none", () => {
    expect(newRunSchema.parse(withConfig({ dataset: "" })).config.dataset).toBeNull();
    expect(newRunSchema.parse(withConfig({ dataset: null })).config.dataset).toBeNull();
    expect(newRunSchema.parse(withConfig({ dataset: " nyu2 " })).config.dataset).toBe("nyu2");
  });

  it("produces bodies the generated client accepts", () => {
    expectTypeOf<NewRunValues>().toExtend<RunCreate>();
    expectTypeOf<NonNullable<ReturnType<typeof estimateBodyOf>>>().toExtend<RunEstimateIn>();
    expectTypeOf<(typeof SEARCH_SOURCES)[number]>().toEqualTypeOf<SearchSource>();
  });
});

describe("estimateBodyOf", () => {
  it("leaves out the topic, which the estimate does not need", () => {
    expect(estimateBodyOf({ ...newRunDefaults(), budget_cap_usd: "2" })).toEqual({
      llm_policy: "auto",
      budget_cap_usd: "2",
      config: { ...RUN_CONFIG_DEFAULTS },
    });
  });

  it("is null while an option it needs is invalid", () => {
    expect(estimateBodyOf(withConfig({ max_papers: 500 }))).toBeNull();
    expect(estimateBodyOf(valid({ budget_cap_usd: "-3" }))).toBeNull();
  });
});

describe("newRunDefaults", () => {
  it("starts from the API defaults with no cap and Auto models", () => {
    expect(newRunDefaults()).toEqual({
      topic: "",
      llm_policy: "auto",
      budget_cap_usd: "",
      config: { ...RUN_CONFIG_DEFAULTS },
    });
  });

  it("takes the options of an earlier run, including no dataset", () => {
    const config: RunConfig = { stages: ["literature", "method"], dataset: null, max_papers: 12 };
    const values = newRunDefaults({
      topic: "Again",
      llm_policy: "free",
      budget_cap_usd: "1.50",
      config,
    });
    expect(values).toMatchObject({
      topic: "Again",
      llm_policy: "free",
      budget_cap_usd: "1.50",
      config: { stages: ["literature", "method"], dataset: "", max_papers: 12, year_from: 2018 },
    });
    expect(newRunSchema.parse(values).config.dataset).toBeNull();
  });

  it("does not share arrays with the defaults", () => {
    const values = newRunDefaults();
    (values.config.sources as string[]).push("core");
    expect(RUN_CONFIG_DEFAULTS.sources).toHaveLength(3);
  });
});

describe("stage helpers", () => {
  it("builds and reads pipeline prefixes", () => {
    expect(stagesThrough("literature")).toEqual(["literature"]);
    expect(stagesThrough("coding")).toEqual(["literature", "method", "coding"]);
    expect(stagesThrough("writing")).toEqual([...STAGE_ORDER]);
    expect(lastStageOf(["literature", "method"])).toBe("method");
    expect(lastStageOf(["method"])).toBeNull();
    expect(lastStageOf([])).toBeNull();
    expect(isPipelinePrefix(["literature", "method", "coding"])).toBe(true);
    expect(isPipelinePrefix(["literature", "coding"])).toBe(false);
    expectTypeOf(stagesThrough).returns.toEqualTypeOf<Stage[]>();
  });
});

describe("wizard steps", () => {
  it("cover every form field exactly once, in order", () => {
    const fields = NEW_RUN_STEPS.flatMap((step) => step.fields);
    expect(new Set(fields).size).toBe(fields.length);
    expect([...fields].sort()).toEqual(
      [
        "topic",
        "llm_policy",
        "budget_cap_usd",
        ...Object.keys(RUN_CONFIG_DEFAULTS).map((key) => `config.${key}`),
      ].sort(),
    );
    expect(NEW_RUN_STEPS.map((step) => step.id)).toEqual([
      "topic",
      "literature",
      "stages",
      "budget",
    ]);
  });

  it("finds the first step with an error", () => {
    const failing = (paths: NewRunFieldPath[]) => (path: NewRunFieldPath) => paths.includes(path);
    expect(firstStepWithError(failing(["budget_cap_usd", "config.sources"]))).toBe(1);
    expect(firstStepWithError(failing(["config.dataset"]))).toBe(2);
    expect(firstStepWithError(failing([]))).toBe(-1);
  });
});

describe("newRunFieldError", () => {
  it("gives the message key and the values it interpolates", () => {
    expect(newRunFieldError({ message: "maxPapers.outOfRange" })).toEqual({
      code: "maxPapers.outOfRange",
      key: "wizard.errors.maxPapers.outOfRange",
      values: { min: 5, max: 50 },
    });
    expect(newRunFieldError({ message: "sources.empty" })?.values).toEqual({});
    expect(newRunFieldError(undefined)).toBeNull();
  });

  it("reads messages that are not ours as rejected by the server", () => {
    expect(newRunFieldError({ message: "Required" })?.code).toBe("server.rejected");
  });

  it("has values for every code", () => {
    for (const code of NEW_RUN_ERROR_CODES) {
      expect(typeof newRunErrorValues(code), code).toBe("object");
    }
  });
});

describe("serverFieldErrors", () => {
  it("maps FastAPI problems to the fields they are about", () => {
    const { fieldErrors, unmatched } = serverFieldErrors([
      {
        loc: ["body", "topic"],
        msg: "String should have at least 3 characters",
        type: "string_too_short",
      },
      {
        loc: ["body", "budget_cap_usd"],
        msg: "Input should be less than or equal to 1000",
        type: "less_than_equal",
      },
      {
        loc: ["body", "config", "max_papers"],
        msg: "Input should be less than or equal to 30",
        type: "less_than_equal",
      },
      {
        loc: ["body", "config", "sources", 1],
        msg: "Input should be 'arxiv', ...",
        type: "literal_error",
      },
      { loc: ["body", "config", "dataset"], msg: "Unknown dataset", type: "value_error" },
    ]);
    expect(fieldErrors).toEqual([
      { path: "topic", code: "topic.tooShort" },
      { path: "budget_cap_usd", code: "budget.tooHigh" },
      { path: "config.max_papers", code: "maxPapers.outOfRange" },
      { path: "config.sources", code: "sources.invalid" },
      { path: "config.dataset", code: "server.rejected" },
    ]);
    expect(unmatched).toBe(0);
  });

  it("places RunConfig's cross-field rules on the field they concern", () => {
    const rule = (msg: string) => ({ loc: ["body", "config"], msg, type: "value_error" });
    expect(
      serverFieldErrors([
        rule("Value error, year_from must not be after year_to"),
        rule("Value error, sources must be unique"),
        rule("Value error, stages must start with literature and follow the pipeline order"),
      ]).fieldErrors,
    ).toEqual([
      { path: "config.year_to", code: "year.order" },
      { path: "config.sources", code: "sources.duplicate" },
      { path: "config.stages", code: "stages.notPrefix" },
    ]);
  });

  it("counts what no field explains and keeps one problem per field", () => {
    const result = serverFieldErrors([
      { loc: ["body"], msg: "Field required", type: "missing" },
      { loc: ["body", "config"], msg: "Value error, something new", type: "value_error" },
      { loc: ["body", "owner_id"], msg: "Extra inputs are not permitted", type: "extra_forbidden" },
      { loc: ["query", "x"], msg: "?", type: "missing" },
      "not a problem",
      { loc: ["body", "topic"], msg: "too short", type: "string_too_short" },
      { loc: ["body", "topic"], msg: "too long", type: "string_too_long" },
    ]);
    expect(result).toEqual({
      fieldErrors: [{ path: "topic", code: "topic.tooShort" }],
      unmatched: 5,
    });
    expect(serverFieldErrors("validation.failed")).toEqual({ fieldErrors: [], unmatched: 0 });
  });
});

describe("NewRunValidationError", () => {
  it("is an ApiError with the validation code and the field problems", () => {
    const error = new NewRunValidationError([{ path: "topic", code: "topic.tooShort" }], 1);
    expect(error).toMatchObject({ code: "validation.failed", status: 422, unmatched: 1 });
    expect(error.fieldErrors).toHaveLength(1);
    expect(error.name).toBe("NewRunValidationError");
  });
});
