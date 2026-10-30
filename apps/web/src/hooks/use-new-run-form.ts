"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  keepPreviousData,
  type UseQueryResult,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { type BaseSyntheticEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { get, type UseFormReturn, useForm, useWatch } from "react-hook-form";
import type { RunCreate, RunEstimateIn, RunEstimateOut, RunOut, Stage } from "@/client";
import { listRecentRunsQueryKey, listRunsQueryKey } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";
import { createRun, estimateRunCost } from "@/client/sdk.gen";
import { type ApiError, toApiError } from "@/lib/api-error";
import {
  estimateBodyOf,
  firstStepWithError,
  NEW_RUN_STEPS,
  type NewRunDefaultsOverrides,
  type NewRunFieldPath,
  type NewRunFormInput,
  type NewRunStep,
  type NewRunStepId,
  NewRunValidationError,
  type NewRunValues,
  newRunDefaults,
  newRunSchema,
  serverFieldErrors,
  stagesThrough,
} from "@/lib/new-run-schema";
import { useDebouncedValue } from "./use-paper-search";

/** How long the options must stay unchanged before the estimate is refreshed. */
export const ESTIMATE_DEBOUNCE_MS = 400;

export type EstimateRunCostQueryKey = readonly [
  { _id: "estimateRunCost"; baseUrl?: string; body: RunEstimateIn | null },
];

/**
 * The cache key of a cost estimate (the generated client has no query options for it, since it
 * is a POST). Invalidate `[{ _id: "estimateRunCost" }]` to refresh every estimate, e.g. after the
 * paid-models switch or a budget changes.
 */
export function estimateRunCostQueryKey(body: RunEstimateIn | null): EstimateRunCostQueryKey {
  return [{ _id: "estimateRunCost", baseUrl: client.getConfig().baseUrl, body }];
}

/**
 * POST /projects/{id}/runs. A 422 with FastAPI's list of problems becomes a NewRunValidationError
 * naming the form fields they are about; the generated client keeps only the code, so the body is
 * read from a copy of the response here.
 */
async function createRunReportingFields(projectId: string, body: RunCreate): Promise<RunOut> {
  const refused: { status?: number; detail?: unknown } = {};
  const send = client.getConfig().fetch ?? globalThis.fetch;
  const fetchKeepingProblems = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await send(input, init);
    if (response.status === 422) {
      refused.status = response.status;
      refused.detail = await response
        .clone()
        .json()
        .then(
          (payload: unknown) =>
            typeof payload === "object" && payload !== null && "detail" in payload
              ? payload.detail
              : undefined,
          () => undefined,
        );
    }
    return response;
  };
  try {
    const { data } = await createRun({
      path: { project_id: projectId },
      body,
      fetch: fetchKeepingProblems,
      throwOnError: true,
    });
    return data;
  } catch (cause) {
    if (Array.isArray(refused.detail)) {
      const { fieldErrors, unmatched } = serverFieldErrors(refused.detail);
      throw new NewRunValidationError(fieldErrors, unmatched, refused.status);
    }
    throw toApiError(cause, refused.status);
  }
}

export type UseNewRunFormOptions = {
  /** Called with the new run once the API has created it (navigate to its page here). */
  onCreated?: (run: RunOut) => void;
  /** Starting values, e.g. an earlier run's topic and options. Read once, on mount. */
  defaultValues?: NewRunDefaultsOverrides;
  /** Debounce of the cost estimate (default 400 ms). */
  estimateDebounceMs?: number;
};

export type NewRunEstimate = {
  /** The estimate query (TanStack), keyed by the options it estimates. */
  query: UseQueryResult<RunEstimateOut, ApiError>;
  /**
   * The latest estimate (a range: low/expected/high USD, why paid models may be blocked, the
   * assumptions per step). While new options are being estimated it keeps the previous figures;
   * undefined while the options are invalid or before the first answer.
   */
  data: RunEstimateOut | undefined;
  /** The current options are valid, so they can be estimated. */
  available: boolean;
  /** The figures are for older options: typing has not settled, or a new estimate is loading. */
  isUpdating: boolean;
  error: ApiError | null;
};

export type NewRunForm = {
  /**
   * The react-hook-form form: `register`, `control` (for Controller), `formState.errors`,
   * `setValue`... Field names are the API's: "topic", "config.max_papers"... Error messages are
   * codes; show them with `newRunFieldError(error)` from src/lib/new-run-schema.ts.
   */
  form: UseFormReturn<NewRunFormInput, unknown, NewRunValues>;
  /** Every step in order, with the fields it edits. */
  steps: readonly NewRunStep[];
  step: NewRunStep;
  stepIndex: number;
  isFirstStep: boolean;
  isLastStep: boolean;
  /** Steps that have a field with an error now (for step badges). */
  stepErrors: Readonly<Record<NewRunStepId, boolean>>;
  /** Validates the current step; moves to the next one when it passes. Resolves to whether it moved. */
  next: () => Promise<boolean>;
  back: () => void;
  /** Any earlier step at once; a later one when every step before it is valid. */
  goTo: (step: NewRunStepId) => Promise<boolean>;
  /** For `<form onSubmit>`: on earlier steps it acts as `next` (Enter moves on), on the last it submits. */
  onSubmit: (event?: BaseSyntheticEvent) => Promise<void>;
  /**
   * Validates everything and creates the run. Invalid fields (the form's or the API's) are shown
   * on their step, and the wizard goes to the first step that has one.
   */
  submit: (event?: BaseSyntheticEvent) => Promise<void>;
  isSubmitting: boolean;
  /** The user has tried to submit at least once. */
  isSubmitted: boolean;
  /** Why creating the run failed, when no field explains it (e.g. `orchestrator.unavailable`). */
  submitError: ApiError | null;
  estimate: NewRunEstimate;
  /** Sets the stages to the pipeline up to and including `stage` ("stop after"). */
  setLastStage: (stage: Stage) => void;
  /** Back to the starting values and the first step. */
  reset: () => void;
};

const LAST_STEP = NEW_RUN_STEPS.length - 1;

function stepIndexOf(id: NewRunStepId): number {
  return NEW_RUN_STEPS.findIndex((step) => step.id === id);
}

function fieldsOfSteps(count: number): NewRunFieldPath[] {
  return NEW_RUN_STEPS.slice(0, count).flatMap((step) => step.fields);
}

/**
 * The new-run wizard of a project, shared by Classic and Studio: a react-hook-form form whose
 * zod schema mirrors the API's RunCreate (src/lib/new-run-schema.ts), its steps, a cost estimate
 * that follows the options, and submission through `createRun`. Creating a run refreshes the
 * project's runs and the recent-runs lists; navigating to the run is up to `onCreated`.
 *
 * Values survive steps whose inputs unmount. Key the wizard by project id: the form keeps its
 * values when `projectId` changes.
 */
export function useNewRunForm(projectId: string, options: UseNewRunFormOptions = {}): NewRunForm {
  const queryClient = useQueryClient();
  const latestOptions = useRef(options);
  useEffect(() => {
    latestOptions.current = options;
  });

  const [initialValues] = useState(() => newRunDefaults(options.defaultValues));
  const form = useForm<NewRunFormInput, unknown, NewRunValues>({
    resolver: zodResolver(newRunSchema),
    defaultValues: initialValues,
    mode: "onTouched",
  });
  const [stepIndex, setStepIndex] = useState(0);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  const submitting = useRef(false);

  // The year order is reported on year_to: re-check it when year_from changes.
  useEffect(
    () =>
      form.subscribe({
        name: "config.year_from",
        formState: { values: true },
        callback: () => {
          const { error, isTouched } = form.getFieldState("config.year_to");
          if (error || isTouched || form.formState.isSubmitted) {
            void form.trigger("config.year_to");
          }
        },
      }),
    [form],
  );

  // Read during render, so the component re-renders when they change (react-hook-form's proxy);
  // isSubmitted is also what the year re-check above reads.
  const { errors, isSubmitting, isSubmitted } = form.formState;
  const stepErrors = Object.fromEntries(
    NEW_RUN_STEPS.map((step) => [step.id, step.fields.some((field) => get(errors, field))]),
  ) as Record<NewRunStepId, boolean>;

  const validate = useCallback(
    async (fields: NewRunFieldPath[]) =>
      fields.length === 0 || form.trigger(fields, { shouldFocus: true }),
    [form],
  );

  const next = useCallback(async () => {
    const from = stepIndex;
    const valid = await validate([...(NEW_RUN_STEPS[from]?.fields ?? [])]);
    if (valid) {
      // A double click validates twice but moves once.
      setStepIndex((current) => (current === from ? Math.min(from + 1, LAST_STEP) : current));
    }
    return valid;
  }, [stepIndex, validate]);

  const back = useCallback(() => setStepIndex((current) => Math.max(0, current - 1)), []);

  const goTo = useCallback(
    async (id: NewRunStepId) => {
      const target = stepIndexOf(id);
      if (target < 0) {
        return false;
      }
      if (target <= stepIndex || (await validate(fieldsOfSteps(target)))) {
        setStepIndex(target);
        return true;
      }
      // getFieldState reads the errors trigger() just set (formState is the last render's).
      const failing = firstStepWithError((path) => Boolean(form.getFieldState(path).error));
      if (failing >= 0 && failing < target) {
        setStepIndex(failing);
      }
      return false;
    },
    [form, stepIndex, validate],
  );

  const create = useMutation<RunOut, ApiError, RunCreate>({
    mutationKey: ["createRun", projectId],
    mutationFn: (body) => createRunReportingFields(projectId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: listRunsQueryKey({ path: { project_id: projectId } }),
      });
      void queryClient.invalidateQueries({ queryKey: listRecentRunsQueryKey() });
    },
  });
  const createRunNow = create.mutateAsync;

  const submit = useMemo(
    () =>
      form.handleSubmit(
        async (values) => {
          if (submitting.current) {
            return;
          }
          submitting.current = true;
          setSubmitError(null);
          try {
            const run = await createRunNow(values);
            latestOptions.current.onCreated?.(run);
          } catch (cause) {
            const fieldErrors = cause instanceof NewRunValidationError ? cause.fieldErrors : [];
            for (const { path, code } of fieldErrors) {
              form.setError(path, { type: "server", message: code });
            }
            const failing = firstStepWithError((path) =>
              fieldErrors.some((error) => error.path === path),
            );
            if (failing >= 0) {
              setStepIndex(failing);
            }
            const explained =
              cause instanceof NewRunValidationError &&
              fieldErrors.length > 0 &&
              cause.unmatched === 0;
            setSubmitError(explained ? null : toApiError(cause));
          } finally {
            submitting.current = false;
          }
        },
        (invalid) => {
          const failing = firstStepWithError((path) => Boolean(get(invalid, path)));
          if (failing >= 0) {
            setStepIndex(failing);
          }
        },
      ),
    [createRunNow, form],
  );

  const onSubmit = useCallback(
    async (event?: BaseSyntheticEvent) => {
      if (stepIndex < LAST_STEP) {
        event?.preventDefault?.();
        await next();
        return;
      }
      await submit(event);
    },
    [next, stepIndex, submit],
  );

  const setLastStage = useCallback(
    (stage: Stage) =>
      form.setValue("config.stages", stagesThrough(stage), {
        shouldDirty: true,
        shouldTouch: true,
        shouldValidate: true,
      }),
    [form],
  );

  const resetCreate = create.reset;
  const reset = useCallback(() => {
    form.reset(initialValues);
    setStepIndex(0);
    setSubmitError(null);
    resetCreate();
  }, [form, initialValues, resetCreate]);

  // The estimate follows the options it depends on (not the topic), once they settle.
  const estimateKey = useWatch({
    control: form.control,
    compute: (values: NewRunFormInput) => {
      const body = estimateBodyOf(values);
      return body ? JSON.stringify(body) : null;
    },
  });
  const settledKey = useDebouncedValue(
    estimateKey,
    options.estimateDebounceMs ?? ESTIMATE_DEBOUNCE_MS,
  );
  const settledBody = useMemo<RunEstimateIn | null>(
    () => (settledKey ? JSON.parse(settledKey) : null),
    [settledKey],
  );
  const estimateQuery = useQuery<RunEstimateOut, ApiError, RunEstimateOut, EstimateRunCostQueryKey>(
    {
      queryKey: estimateRunCostQueryKey(settledBody),
      queryFn: async ({ queryKey, signal }) => {
        const { data } = await estimateRunCost({
          body: queryKey[0].body ?? {},
          signal,
          throwOnError: true,
        });
        return data;
      },
      enabled: settledBody !== null,
      placeholderData: keepPreviousData,
      staleTime: 30_000,
    },
  );

  return {
    form,
    steps: NEW_RUN_STEPS,
    step: NEW_RUN_STEPS[stepIndex] ?? NEW_RUN_STEPS[0],
    stepIndex,
    isFirstStep: stepIndex === 0,
    isLastStep: stepIndex === LAST_STEP,
    stepErrors,
    next,
    back,
    goTo,
    onSubmit,
    submit,
    isSubmitting,
    isSubmitted,
    submitError,
    estimate: {
      query: estimateQuery,
      data: estimateKey === null ? undefined : estimateQuery.data,
      available: estimateKey !== null,
      isUpdating:
        estimateKey !== settledKey || (estimateQuery.isFetching && estimateQuery.isPlaceholderData),
      error: estimateQuery.error,
    },
    setLastStage,
    reset,
  };
}
