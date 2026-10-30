"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { type UseQueryResult, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type BaseSyntheticEvent, useCallback, useState } from "react";
import { type UseFormReturn, useForm } from "react-hook-form";
import { z } from "zod";
import type { GetProjectSettingsError, ProjectSettings } from "@/client";
import {
  getProjectQueryKey,
  getProjectSettingsOptions,
  listProjectsQueryKey,
  updateProjectSettingsMutation,
} from "@/client/@tanstack/react-query.gen";
import { ApiError, toApiError } from "@/lib/api-error";
import { wholeNumberField } from "@/lib/new-run-schema";
import type { ActionResult } from "./use-members";

/** The settings' cache key, typed with their data. */
function settingsKey(projectId: string) {
  return getProjectSettingsOptions({ path: { project_id: projectId } }).queryKey;
}

/** What the API creates a project with; the form shows these only until the settings load. */
export const PROJECT_SETTINGS_DEFAULTS: Readonly<ProjectSettings> = {
  privacy: "standard",
  allow_free_models: true,
  auto_approve: false,
  approval_expiry_days: 7,
};

export const PROJECT_SETTINGS_LIMITS = { approvalExpiryDays: { min: 1, max: 30 } } as const;

/** Message codes of field errors; each has a message at `project.settings.errors.<code>`. */
export const PROJECT_SETTINGS_ERROR_CODES = [
  "privacy.invalid",
  "value.invalid",
  "approvalExpiryDays.invalid",
  "approvalExpiryDays.outOfRange",
] as const;

export type ProjectSettingsErrorCode = (typeof PROJECT_SETTINGS_ERROR_CODES)[number];

/** Mirrors the API's ProjectSettings (all fields required, expiry 1..30 days). */
export const projectSettingsSchema = z.object({
  privacy: z.enum(["standard", "confidential"], { error: "privacy.invalid" }),
  allow_free_models: z.boolean({ error: "value.invalid" }),
  auto_approve: z.boolean({ error: "value.invalid" }),
  approval_expiry_days: wholeNumberField(
    PROJECT_SETTINGS_LIMITS.approvalExpiryDays.min,
    PROJECT_SETTINGS_LIMITS.approvalExpiryDays.max,
    { invalid: "approvalExpiryDays.invalid", outOfRange: "approvalExpiryDays.outOfRange" },
  ),
});

export type ProjectSettingsFormInput = z.input<typeof projectSettingsSchema>;

/** The message for a field error of the settings form, or null without one. */
export function projectSettingsFieldError(
  error: { message?: string | undefined } | null | undefined,
): {
  code: ProjectSettingsErrorCode;
  key: `project.settings.errors.${ProjectSettingsErrorCode}`;
  values: Record<string, number>;
} | null {
  if (!error) {
    return null;
  }
  const code = (PROJECT_SETTINGS_ERROR_CODES as readonly string[]).includes(error.message ?? "")
    ? (error.message as ProjectSettingsErrorCode)
    : "value.invalid";
  return {
    code,
    key: `project.settings.errors.${code}`,
    values: code.startsWith("approvalExpiryDays")
      ? { ...PROJECT_SETTINGS_LIMITS.approvalExpiryDays }
      : {},
  };
}

export type ProjectSettingsState = {
  /** The settings query (TanStack). Every member may read them. */
  query: UseQueryResult<ProjectSettings, GetProjectSettingsError>;
  /** The settings, including saves still on their way (optimistic); undefined until loaded. */
  settings: ProjectSettings | undefined;
  /**
   * A react-hook-form form over the settings. It follows the saved settings (and other people's
   * changes when they reload) without overwriting fields the user is editing.
   */
  form: UseFormReturn<ProjectSettingsFormInput, unknown, ProjectSettings>;
  /** The form has edits that are not saved yet (enable a Save button). */
  isDirty: boolean;
  /** For `<form onSubmit>`: validates and saves every field, then marks the form as saved. */
  submit: (event?: BaseSyntheticEvent) => Promise<void>;
  /**
   * Saves some fields now (switches that apply at once), on top of the latest settings. Shown at
   * once, put back if the API refuses. Owners and lab admins only (403 `permission.denied`).
   */
  update: (patch: Partial<ProjectSettings>) => Promise<ActionResult<ProjectSettings>>;
  isSaving: boolean;
  /** Why the last save failed; cleared when the next one starts. */
  saveError: ApiError | null;
  clearSaveError: () => void;
};

/**
 * A project's settings (privacy, free models, auto-approve, approval expiry): read for every
 * member, saved by owners and lab admins. Saves are optimistic and run one after another, so the
 * last change wins; a save also refreshes the project (its privacy and free-model flags).
 */
export function useProjectSettings(projectId: string): ProjectSettingsState {
  const queryClient = useQueryClient();
  const query = useQuery({
    ...getProjectSettingsOptions({ path: { project_id: projectId } }),
    staleTime: 30_000,
  });
  const settings = query.data;
  const form = useForm<ProjectSettingsFormInput, unknown, ProjectSettings>({
    resolver: zodResolver(projectSettingsSchema),
    defaultValues: PROJECT_SETTINGS_DEFAULTS,
    values: settings,
    resetOptions: { keepDirtyValues: true },
    mode: "onTouched",
  });
  const [saveError, setSaveError] = useState<ApiError | null>(null);

  const mutationKey = ["updateProjectSettings", projectId];
  const isOnlySave = () => queryClient.isMutating({ mutationKey }) === 1;
  const mutation = useMutation({
    ...updateProjectSettingsMutation(),
    mutationKey,
    // One save at a time, in order: the last change always wins.
    scope: { id: `project-settings:${projectId}` },
    onMutate: async (variables) => {
      const key = settingsKey(variables.path.project_id);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData(key);
      queryClient.setQueryData(key, variables.body);
      return { previous };
    },
    onError: (_error, variables, context) => {
      // With other saves queued, they carry this change on; their outcome decides.
      if (isOnlySave() && context?.previous) {
        queryClient.setQueryData(settingsKey(variables.path.project_id), context.previous);
      }
    },
    onSuccess: (saved, variables) => {
      if (isOnlySave()) {
        queryClient.setQueryData(settingsKey(variables.path.project_id), saved);
      }
    },
    onSettled: (_saved, _error, variables) => {
      if (isOnlySave()) {
        void queryClient.invalidateQueries({
          queryKey: settingsKey(variables.path.project_id),
        });
        void queryClient.invalidateQueries({
          queryKey: getProjectQueryKey({ path: variables.path }),
        });
        void queryClient.invalidateQueries({ queryKey: listProjectsQueryKey() });
      }
    },
  });
  const { mutateAsync } = mutation;

  const save = useCallback(
    async (body: ProjectSettings): Promise<ActionResult<ProjectSettings>> => {
      setSaveError(null);
      try {
        return { ok: true, data: await mutateAsync({ path: { project_id: projectId }, body }) };
      } catch (cause) {
        const error = toApiError(cause);
        setSaveError(error);
        return { ok: false, error };
      }
    },
    [mutateAsync, projectId],
  );

  const update = useCallback(
    async (patch: Partial<ProjectSettings>): Promise<ActionResult<ProjectSettings>> => {
      const current = queryClient.getQueryData(settingsKey(projectId));
      if (!current) {
        const error = new ApiError("unknown");
        setSaveError(error);
        return { ok: false, error };
      }
      const result = await save({
        privacy: patch.privacy ?? current.privacy,
        allow_free_models: patch.allow_free_models ?? current.allow_free_models,
        auto_approve: patch.auto_approve ?? current.auto_approve,
        approval_expiry_days: patch.approval_expiry_days ?? current.approval_expiry_days,
      });
      if (result.ok) {
        // Saved fields are no longer unsaved edits of the form.
        const saved = result.data;
        if (patch.privacy !== undefined) {
          form.resetField("privacy", { defaultValue: saved.privacy });
        }
        if (patch.allow_free_models !== undefined) {
          form.resetField("allow_free_models", { defaultValue: saved.allow_free_models });
        }
        if (patch.auto_approve !== undefined) {
          form.resetField("auto_approve", { defaultValue: saved.auto_approve });
        }
        if (patch.approval_expiry_days !== undefined) {
          form.resetField("approval_expiry_days", { defaultValue: saved.approval_expiry_days });
        }
      }
      return result;
    },
    [form, projectId, queryClient, save],
  );

  const submit = form.handleSubmit(async (values) => {
    const result = await save(values);
    if (result.ok) {
      // reset() applies the form's resetOptions: the saved edits must not be kept as "dirty".
      form.reset(result.data, { keepDirtyValues: false });
    }
  });

  const clearSaveError = useCallback(() => setSaveError(null), []);

  return {
    query,
    settings,
    form,
    // Reading it here subscribes the component, so it re-renders when it changes.
    isDirty: form.formState.isDirty,
    submit,
    update,
    isSaving: mutation.isPending,
    saveError,
    clearSaveError,
  };
}
