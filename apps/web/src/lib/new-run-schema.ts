import { z } from "zod";
import type { LlmPolicy, RunConfig, RunConfigOut, RunEstimateIn, Stage } from "@/client";
import { ApiError } from "./api-error";
import { STAGE_ORDER } from "./timeline";

/**
 * The new-run wizard's form, shared by Classic and Studio (src/hooks/use-new-run-form.ts).
 *
 * `newRunSchema` mirrors the API's `RunCreate` and `RunConfig` (apps/api/src/agentic_api/
 * schemas.py, packages/core/src/agentic_core/schemas.py): whatever passes here, the API
 * accepts. Its output is a ready `RunCreate` body.
 *
 * Field errors carry message codes (`NewRunErrorCode`) instead of text. Translate them with
 * `newRunFieldError(error)`, which gives a key under `wizard.errors.*` and the values the
 * message needs (`min`, `max`).
 */

export type SearchSource = NonNullable<RunConfig["sources"]>[number];

/** Literature sources a run can search, in display order. */
export const SEARCH_SOURCES = [
  "arxiv",
  "semantic_scholar",
  "openalex",
  "crossref",
  "core",
] as const satisfies readonly SearchSource[];

export const LLM_POLICIES = ["auto", "free"] as const satisfies readonly LlmPolicy[];

/** The API's RunConfig defaults (a run created without options gets these). Do not mutate. */
export const RUN_CONFIG_DEFAULTS: Readonly<RunConfigOut> = {
  year_from: 2018,
  year_to: 2026,
  sources: ["arxiv", "semantic_scholar", "openalex"],
  max_papers: 20,
  stages: [...STAGE_ORDER],
  dataset: "nyu2",
};

/** Bounds of the API, also the values of the matching error messages. */
export const NEW_RUN_LIMITS = {
  topic: { min: 3, max: 500 },
  year: { min: 1990, max: 2100 },
  maxPapers: { min: 5, max: 50 },
  budget: { min: 0, max: 1000 },
} as const;

/** Message codes of field errors; each has a message at `wizard.errors.<code>`. */
export const NEW_RUN_ERROR_CODES = [
  "topic.tooShort",
  "topic.tooLong",
  "year.invalid",
  "year.outOfRange",
  "year.order",
  "sources.empty",
  "sources.invalid",
  "sources.duplicate",
  "maxPapers.invalid",
  "maxPapers.outOfRange",
  "stages.empty",
  "stages.invalid",
  "stages.notPrefix",
  "dataset.invalid",
  "llmPolicy.invalid",
  "budget.invalid",
  "budget.negative",
  "budget.tooHigh",
  // The API refused the value for a reason the form does not check itself.
  "server.rejected",
] as const;

export type NewRunErrorCode = (typeof NEW_RUN_ERROR_CODES)[number];

const KNOWN_ERROR_CODES = new Set<string>(NEW_RUN_ERROR_CODES);

export function isNewRunErrorCode(value: unknown): value is NewRunErrorCode {
  return typeof value === "string" && KNOWN_ERROR_CODES.has(value);
}

// --- Stages and sources -------------------------------------------------------------------------

export function isStage(value: unknown): value is Stage {
  return typeof value === "string" && (STAGE_ORDER as readonly string[]).includes(value);
}

export function isSearchSource(value: unknown): value is SearchSource {
  return typeof value === "string" && (SEARCH_SOURCES as readonly string[]).includes(value);
}

/** Whether `stages` start with literature and follow the pipeline order (RunConfig's rule). */
export function isPipelinePrefix(stages: readonly string[]): boolean {
  return (
    stages.length <= STAGE_ORDER.length &&
    stages.every((stage, index) => stage === STAGE_ORDER[index])
  );
}

/** The stages a run that stops after `last` goes through, for "stop after" pickers. */
export function stagesThrough(last: Stage): Stage[] {
  return STAGE_ORDER.slice(0, STAGE_ORDER.indexOf(last) + 1);
}

/** The stage a run with these stages stops after, or null when they are not a valid prefix. */
export function lastStageOf(stages: readonly string[]): Stage | null {
  const last = stages.at(-1);
  return isStage(last) && isPipelinePrefix(stages) ? last : null;
}

// --- Field schemas ------------------------------------------------------------------------------

/** What number inputs hand over: a number (`valueAsNumber`, NumberField), text, or nothing. */
export type NumberInput = number | string | null | undefined;

const DECIMAL = /^-?\d+(\.\d+)?$/;

/** A number from an input, or NaN for anything that is not plainly one. */
function numberFrom(value: unknown): number {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string" && DECIMAL.test(value.trim())) {
    return Number(value.trim());
  }
  return Number.NaN;
}

/** A whole number between `min` and `max`, from whatever a number input hands over. */
export function wholeNumberField<Code extends string>(
  min: number,
  max: number,
  codes: { invalid: Code; outOfRange: Code },
) {
  return z.custom<NumberInput>().transform((value, ctx) => {
    const number = numberFrom(value);
    if (!Number.isInteger(number)) {
      ctx.addIssue({ code: "custom", message: codes.invalid });
      return z.NEVER;
    }
    if (number < min || number > max) {
      ctx.addIssue({ code: "custom", message: codes.outOfRange });
      return z.NEVER;
    }
    return number;
  });
}

/** Python's len(): code points, not UTF-16 units. */
function length(text: string): number {
  return Array.from(text).length;
}

const topicSchema = z
  .string({ error: "topic.tooShort" })
  .trim()
  .refine((topic) => length(topic) >= NEW_RUN_LIMITS.topic.min, { error: "topic.tooShort" })
  .refine((topic) => length(topic) <= NEW_RUN_LIMITS.topic.max, { error: "topic.tooLong" });

const llmPolicySchema = z.enum(LLM_POLICIES, { error: "llmPolicy.invalid" });

/** An empty input means "no cap"; anything else is sent as the decimal string the user typed. */
export type BudgetInput = number | string | null | undefined;

const budgetSchema = z.custom<BudgetInput>().transform((value, ctx): string | null => {
  const fail = (code: NewRunErrorCode) => {
    ctx.addIssue({ code: "custom", message: code });
    return z.NEVER;
  };
  if (value === null || value === undefined || (typeof value === "number" && Number.isNaN(value))) {
    return null;
  }
  let amount: number;
  let decimal: string;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return fail("budget.invalid");
    }
    amount = value;
    decimal = String(value);
  } else if (typeof value === "string") {
    decimal = value.trim();
    if (decimal === "") {
      return null;
    }
    if (!DECIMAL.test(decimal)) {
      return fail("budget.invalid");
    }
    amount = Number(decimal);
  } else {
    return fail("budget.invalid");
  }
  if (amount < NEW_RUN_LIMITS.budget.min) {
    return fail("budget.negative");
  }
  if (amount > NEW_RUN_LIMITS.budget.max) {
    return fail("budget.tooHigh");
  }
  return decimal;
});

const yearSchema = wholeNumberField(NEW_RUN_LIMITS.year.min, NEW_RUN_LIMITS.year.max, {
  invalid: "year.invalid",
  outOfRange: "year.outOfRange",
} as const);

const maxPapersSchema = wholeNumberField(
  NEW_RUN_LIMITS.maxPapers.min,
  NEW_RUN_LIMITS.maxPapers.max,
  { invalid: "maxPapers.invalid", outOfRange: "maxPapers.outOfRange" } as const,
);

const sourcesSchema = z
  .array(z.string(), { error: "sources.invalid" })
  .min(1, { error: "sources.empty" })
  .refine((sources) => sources.every(isSearchSource), { error: "sources.invalid" })
  .refine((sources) => new Set(sources).size === sources.length, { error: "sources.duplicate" })
  .transform((sources) => sources as SearchSource[]);

const stagesSchema = z
  .array(z.string(), { error: "stages.invalid" })
  .min(1, { error: "stages.empty" })
  .refine((stages) => stages.every(isStage), { error: "stages.invalid" })
  .refine(isPipelinePrefix, { error: "stages.notPrefix" })
  .transform((stages) => stages as Stage[]);

/** A dataset id (see GET /api/v1/datasets); an empty choice means none. */
const datasetSchema = z.custom<string | null | undefined>().transform((value, ctx) => {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string") {
    ctx.addIssue({ code: "custom", message: "dataset.invalid" });
    return z.NEVER;
  }
  return value.trim() === "" ? null : value.trim();
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** RunConfig: the literature, stage and dataset options. */
export const runConfigSchema = z
  .object({
    year_from: yearSchema,
    year_to: yearSchema,
    sources: sourcesSchema,
    max_papers: maxPapersSchema,
    stages: stagesSchema,
    dataset: datasetSchema,
  })
  .refine((config) => config.year_from <= config.year_to, {
    error: "year.order",
    path: ["year_to"],
    // Compare as soon as both years are valid, whatever else is still wrong.
    when: ({ value }) =>
      isRecord(value) && Number.isInteger(value.year_from) && Number.isInteger(value.year_to),
  });

/** The whole wizard; the output is a `RunCreate` body. */
export const newRunSchema = z.object({
  topic: topicSchema,
  llm_policy: llmPolicySchema,
  budget_cap_usd: budgetSchema,
  config: runConfigSchema,
});

/** The options the cost estimate depends on; the output is a `RunEstimateIn` body. */
export const runEstimateSchema = z.object({
  llm_policy: llmPolicySchema,
  budget_cap_usd: budgetSchema,
  config: runConfigSchema,
});

/** The wizard's form values, as inputs hold them. */
export type NewRunFormInput = z.input<typeof newRunSchema>;
/** Valid form values, normalised: the body of `POST /projects/{id}/runs`. */
export type NewRunValues = z.output<typeof newRunSchema>;

/** The estimate request for these form values, or null while any option it needs is invalid. */
export function estimateBodyOf(values: NewRunFormInput): RunEstimateIn | null {
  const parsed = runEstimateSchema.safeParse({
    llm_policy: values.llm_policy,
    budget_cap_usd: values.budget_cap_usd,
    config: values.config,
  });
  return parsed.success ? parsed.data : null;
}

// --- Defaults -----------------------------------------------------------------------------------

/** Starting values, e.g. the options of an earlier run (`RunOut` fields fit as they are). */
export type NewRunDefaultsOverrides = {
  topic?: string;
  llm_policy?: LlmPolicy;
  budget_cap_usd?: BudgetInput;
  config?: RunConfig;
};

/** The wizard's initial values: the API defaults, no cost cap, Auto models, and any overrides. */
export function newRunDefaults(overrides: NewRunDefaultsOverrides = {}): NewRunFormInput {
  const config = overrides.config ?? {};
  const defaults = RUN_CONFIG_DEFAULTS;
  const dataset = config.dataset === undefined ? defaults.dataset : config.dataset;
  return {
    topic: overrides.topic ?? "",
    llm_policy: overrides.llm_policy ?? "auto",
    budget_cap_usd: overrides.budget_cap_usd ?? "",
    config: {
      year_from: config.year_from ?? defaults.year_from,
      year_to: config.year_to ?? defaults.year_to,
      sources: [...(config.sources ?? defaults.sources)],
      max_papers: config.max_papers ?? defaults.max_papers,
      stages: [...(config.stages ?? defaults.stages)],
      // Selects hold "" for "no dataset"; the schema turns it back into null.
      dataset: dataset ?? "",
    },
  };
}

// --- Wizard steps -------------------------------------------------------------------------------

export type NewRunFieldPath =
  | "topic"
  | "llm_policy"
  | "budget_cap_usd"
  | `config.${keyof RunConfigOut}`;

export type NewRunStepId = "topic" | "literature" | "stages" | "budget";

export type NewRunStep = {
  id: NewRunStepId;
  /** The fields the step edits; moving on validates exactly these. */
  fields: readonly NewRunFieldPath[];
};

/** The wizard's steps in order: topic; literature options; stages and dataset; models and budget. */
export const NEW_RUN_STEPS: readonly [NewRunStep, ...NewRunStep[]] = [
  { id: "topic", fields: ["topic"] },
  {
    id: "literature",
    fields: ["config.year_from", "config.year_to", "config.sources", "config.max_papers"],
  },
  { id: "stages", fields: ["config.stages", "config.dataset"] },
  { id: "budget", fields: ["llm_policy", "budget_cap_usd"] },
];

/** The index of the first step with a field for which `hasError` holds, or -1. */
export function firstStepWithError(hasError: (path: NewRunFieldPath) => boolean): number {
  return NEW_RUN_STEPS.findIndex((step) => step.fields.some(hasError));
}

// --- Messages -----------------------------------------------------------------------------------

export type NewRunErrorMessageKey = `wizard.errors.${NewRunErrorCode}`;

export type NewRunFieldMessage = {
  code: NewRunErrorCode;
  /** For `t(key, values)` with `useTranslations()` (no namespace). */
  key: NewRunErrorMessageKey;
  values: Record<string, number>;
};

/** The `min` and `max` a code's message mentions (e.g. "between {min} and {max}"). */
export function newRunErrorValues(code: NewRunErrorCode): Record<string, number> {
  switch (code.slice(0, code.indexOf("."))) {
    case "topic":
      return { ...NEW_RUN_LIMITS.topic };
    case "year":
      return { ...NEW_RUN_LIMITS.year };
    case "maxPapers":
      return { ...NEW_RUN_LIMITS.maxPapers };
    case "budget":
      return { ...NEW_RUN_LIMITS.budget };
    default:
      return {};
  }
}

/**
 * The message for a field error of the form (`formState.errors.<field>`), or null without one.
 * Errors that are not one of our codes (e.g. from extra `rules`) read as "server.rejected".
 */
export function newRunFieldError(
  error: { message?: string | undefined } | null | undefined,
): NewRunFieldMessage | null {
  if (!error) {
    return null;
  }
  const code: NewRunErrorCode = isNewRunErrorCode(error.message)
    ? error.message
    : "server.rejected";
  return { code, key: `wizard.errors.${code}`, values: newRunErrorValues(code) };
}

// --- Server validation errors -------------------------------------------------------------------

export type ServerFieldError = { path: NewRunFieldPath; code: NewRunErrorCode };

/**
 * `POST /projects/{id}/runs` answered 422 with FastAPI's list of problems. `fieldErrors` are the
 * ones a form field explains; `unmatched` counts the rest. It is still an ApiError
 * (`validation.failed`), so every error helper keeps working with it.
 */
export class NewRunValidationError extends ApiError {
  readonly fieldErrors: readonly ServerFieldError[];
  readonly unmatched: number;

  constructor(fieldErrors: readonly ServerFieldError[], unmatched: number, status = 422) {
    super("validation.failed", status);
    this.name = "NewRunValidationError";
    this.fieldErrors = fieldErrors;
    this.unmatched = unmatched;
  }
}

const BODY_FIELDS = new Set<string>(["topic", "llm_policy", "budget_cap_usd"]);
const CONFIG_FIELDS = new Set<string>(Object.keys(RUN_CONFIG_DEFAULTS));
const RANGE_TYPES = new Set(["greater_than", "greater_than_equal", "less_than", "less_than_equal"]);

/** Our code for a pydantic error `type` on a field; "server.rejected" when unsure. */
function codeFor(path: NewRunFieldPath, type: string): NewRunErrorCode {
  switch (path) {
    case "topic":
      if (type === "string_too_short") {
        return "topic.tooShort";
      }
      return type === "string_too_long" ? "topic.tooLong" : "server.rejected";
    case "llm_policy":
      return type === "enum" ? "llmPolicy.invalid" : "server.rejected";
    case "budget_cap_usd":
      if (type === "greater_than_equal") {
        return "budget.negative";
      }
      if (type === "less_than_equal") {
        return "budget.tooHigh";
      }
      return type.startsWith("decimal") ? "budget.invalid" : "server.rejected";
    case "config.year_from":
    case "config.year_to":
      if (RANGE_TYPES.has(type)) {
        return "year.outOfRange";
      }
      return type.startsWith("int") ? "year.invalid" : "server.rejected";
    case "config.max_papers":
      if (RANGE_TYPES.has(type)) {
        return "maxPapers.outOfRange";
      }
      return type.startsWith("int") ? "maxPapers.invalid" : "server.rejected";
    case "config.sources":
      if (type === "too_short") {
        return "sources.empty";
      }
      return type === "literal_error" ? "sources.invalid" : "server.rejected";
    case "config.stages":
      if (type === "too_short") {
        return "stages.empty";
      }
      return type === "enum" ? "stages.invalid" : "server.rejected";
    default:
      return "server.rejected";
  }
}

/** RunConfig's cross-field rules fail on `config` itself; their messages name the fields. */
function configRuleError(message: string): ServerFieldError | null {
  if (message.includes("year_from") || message.includes("year_to")) {
    return { path: "config.year_to", code: "year.order" };
  }
  if (message.includes("sources")) {
    return { path: "config.sources", code: "sources.duplicate" };
  }
  if (message.includes("stages")) {
    return { path: "config.stages", code: "stages.notPrefix" };
  }
  return null;
}

function fieldErrorOf(problem: unknown): ServerFieldError | null {
  if (!isRecord(problem) || !Array.isArray(problem.loc) || problem.loc[0] !== "body") {
    return null;
  }
  const type = typeof problem.type === "string" ? problem.type : "";
  const [field, part] = problem.loc.slice(1) as unknown[];
  if (typeof field === "string" && BODY_FIELDS.has(field)) {
    const path = field as NewRunFieldPath;
    return { path, code: codeFor(path, type) };
  }
  if (field !== "config") {
    return null;
  }
  if (part === undefined) {
    return configRuleError(typeof problem.msg === "string" ? problem.msg : "");
  }
  if (typeof part === "string" && CONFIG_FIELDS.has(part)) {
    // Problems with one source or stage (loc ends in its index) belong to the list field.
    const path = `config.${part}` as NewRunFieldPath;
    return { path, code: codeFor(path, type) };
  }
  return null;
}

/**
 * Maps FastAPI's 422 `detail` (a list of `{loc, msg, type}`) to form fields. Each field keeps its
 * first problem; problems no field explains are counted in `unmatched`.
 */
export function serverFieldErrors(detail: unknown): {
  fieldErrors: ServerFieldError[];
  unmatched: number;
} {
  const fieldErrors: ServerFieldError[] = [];
  let unmatched = 0;
  for (const problem of Array.isArray(detail) ? detail : []) {
    const error = fieldErrorOf(problem);
    if (!error) {
      unmatched += 1;
    } else if (!fieldErrors.some((known) => known.path === error.path)) {
      fieldErrors.push(error);
    }
  }
  return { fieldErrors, unmatched };
}
