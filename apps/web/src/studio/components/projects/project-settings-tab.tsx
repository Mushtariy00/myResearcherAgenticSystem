"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { Switch } from "@base-ui/react/switch";
import { LockIcon, LockOpenIcon, SaveIcon, ShieldCheckIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useId } from "react";
import { Controller } from "react-hook-form";
import { toast } from "sonner";
import {
  PROJECT_SETTINGS_LIMITS,
  projectSettingsFieldError,
  useProjectSettings,
} from "@/hooks/use-project-settings";
import { cn } from "@/lib/utils";
import {
  FieldError,
  STUDIO_FIELD,
  STUDIO_HINT,
  STUDIO_LABEL,
} from "@/studio/components/dashboard/studio-fields";
import { StudioInlineError, StudioPanel } from "@/studio/components/dashboard/studio-panel";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { useOptionalMessage } from "@/studio/lib/messages";
import { GHOST_BUTTON } from "@/studio/lib/ui";

const CARD =
  "relative flex cursor-pointer items-start gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3 transition-colors hover:bg-(--studio-hover) has-[[data-checked]]:border-(--tone) has-[[data-checked]]:bg-(--tone)/10 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50 has-[[data-readonly]]:cursor-default has-[[data-readonly]]:hover:bg-(--studio-glass)";

function SettingSwitch({
  checked,
  onCheckedChange,
  onBlur,
  label,
  description,
  readOnly,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onBlur: () => void;
  label: string;
  description: string;
  readOnly: boolean;
}) {
  const ids = useId();
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3">
      <div className="grid min-w-0 gap-0.5">
        <span id={`${ids}-label`} className={STUDIO_LABEL}>
          {label}
        </span>
        <span id={`${ids}-description`} className={STUDIO_HINT}>
          {description}
        </span>
      </div>
      <Switch.Root
        checked={checked}
        onCheckedChange={(next) => onCheckedChange(next)}
        onBlur={onBlur}
        readOnly={readOnly}
        aria-labelledby={`${ids}-label`}
        aria-describedby={`${ids}-description`}
        className="relative mt-0.5 inline-flex h-6 w-10 shrink-0 cursor-pointer items-center rounded-full border border-(--studio-glass-border) bg-[color-mix(in_oklch,var(--foreground)_14%,transparent)] p-0.5 outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 data-checked:border-transparent data-checked:bg-(--primary) data-readonly:cursor-not-allowed data-readonly:opacity-70"
      >
        <Switch.Thumb className="block size-4.5 rounded-full bg-white shadow-sm transition-transform duration-200 data-checked:translate-x-4 motion-reduce:transition-none" />
      </Switch.Root>
    </div>
  );
}

/**
 * The project's settings (useProjectSettings): privacy, free models, automatic approval and how
 * long an approval may wait. Owners and lab admins edit and save them; every other member sees
 * the same form read-only, with a note saying who can change it.
 */
export function ProjectSettingsTab({
  projectId,
  canEdit,
}: {
  projectId: string;
  canEdit: boolean;
}) {
  const t = useTranslations("studioWork.project.settings");
  const tCommon = useTranslations("common");
  const optional = useOptionalMessage();
  const ids = useId();
  const state = useProjectSettings(projectId);
  const { form } = state;
  const readOnly = !canEdit;

  function fieldError(error: { message?: string | undefined } | undefined): string | null {
    const field = projectSettingsFieldError(error);
    if (!field) {
      return null;
    }
    return optional(field.key, field.values) ?? t(`errors.${field.code}`, field.values);
  }

  // Saves every field at once; `update` answers with the outcome, so success can be told.
  const save = form.handleSubmit(async (values) => {
    const result = await state.update(values);
    if (result.ok) {
      toast.success(t("saved"));
    }
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    if (readOnly) {
      event.preventDefault();
      return;
    }
    void save(event);
  }

  if (state.query.isPending) {
    return (
      <div className="grid gap-3" aria-busy="true">
        <LoadingStatus label={tCommon("loading")} />
        <ShimmerSkeleton className="h-28 rounded-2xl" />
        <ShimmerSkeleton className="h-16 rounded-xl" />
        <ShimmerSkeleton className="h-16 rounded-xl" />
      </div>
    );
  }
  if (state.query.isError) {
    return <StudioInlineError error={state.query.error} onRetry={() => state.query.refetch()} />;
  }

  const expiryError = fieldError(form.formState.errors.approval_expiry_days);
  const { min, max } = PROJECT_SETTINGS_LIMITS.approvalExpiryDays;

  return (
    <StudioPanel
      id="studio-settings"
      title={t("title")}
      description={canEdit ? t("description") : undefined}
      className="max-w-3xl"
    >
      {readOnly && (
        <p
          data-tone="info"
          className="flex items-start gap-2 rounded-xl border border-(--tone)/25 bg-(--tone)/10 px-3 py-2 text-sm text-foreground"
        >
          <ShieldCheckIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-(--tone-fg)" />
          {t("readOnly")}
        </p>
      )}
      <form onSubmit={onSubmit} noValidate className="grid gap-6" aria-label={t("title")}>
        <Controller
          control={form.control}
          name="privacy"
          render={({ field }) => (
            <div className="grid gap-2">
              <p id={`${ids}-privacy`} className={STUDIO_LABEL}>
                {t("privacy.label")}
              </p>
              <RadioGroup
                value={field.value}
                readOnly={readOnly}
                onValueChange={(next) => {
                  if (next === "standard" || next === "confidential") {
                    field.onChange(next);
                    field.onBlur();
                  }
                }}
                aria-labelledby={`${ids}-privacy`}
                className="grid gap-3 sm:grid-cols-2"
              >
                {(["standard", "confidential"] as const).map((privacy) => {
                  const Icon = privacy === "standard" ? LockOpenIcon : LockIcon;
                  return (
                    // biome-ignore lint/a11y/noLabelWithoutControl: Base UI's Radio renders its input in the label
                    <label
                      key={privacy}
                      data-tone={privacy === "standard" ? "info" : "warning"}
                      className={CARD}
                    >
                      <Radio.Root
                        value={privacy}
                        aria-labelledby={`${ids}-${privacy}`}
                        aria-describedby={`${ids}-${privacy}-description`}
                        className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border-2 border-[color-mix(in_oklch,var(--foreground)_30%,transparent)] outline-none data-checked:border-(--tone)"
                      >
                        <Radio.Indicator className="size-2.5 rounded-full bg-(--tone)" />
                      </Radio.Root>
                      <span className="grid min-w-0 gap-1">
                        <span
                          id={`${ids}-${privacy}`}
                          className="flex items-center gap-2 text-sm font-semibold text-foreground"
                        >
                          <Icon aria-hidden className="size-4 text-(--tone-fg)" />
                          {t(`privacy.${privacy}`)}
                        </span>
                        <span
                          id={`${ids}-${privacy}-description`}
                          className="text-xs text-pretty text-muted-foreground"
                        >
                          {t(`privacy.${privacy}Description`)}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </RadioGroup>
            </div>
          )}
        />

        <div className="grid gap-3">
          <Controller
            control={form.control}
            name="allow_free_models"
            render={({ field }) => (
              <SettingSwitch
                checked={Boolean(field.value)}
                onCheckedChange={field.onChange}
                onBlur={field.onBlur}
                label={t("freeModels.label")}
                description={t("freeModels.description")}
                readOnly={readOnly}
              />
            )}
          />
          <Controller
            control={form.control}
            name="auto_approve"
            render={({ field }) => (
              <SettingSwitch
                checked={Boolean(field.value)}
                onCheckedChange={field.onChange}
                onBlur={field.onBlur}
                label={t("autoApprove.label")}
                description={t("autoApprove.description")}
                readOnly={readOnly}
              />
            )}
          />
        </div>

        <div className="grid gap-1.5 sm:max-w-xs">
          <label htmlFor={`${ids}-expiry`} className={STUDIO_LABEL}>
            {t("expiry.label")}
          </label>
          <input
            id={`${ids}-expiry`}
            type="number"
            inputMode="numeric"
            min={min}
            max={max}
            readOnly={readOnly}
            aria-invalid={expiryError ? true : undefined}
            aria-describedby={[`${ids}-expiry-hint`, expiryError ? `${ids}-expiry-error` : null]
              .filter(Boolean)
              .join(" ")}
            className={cn(STUDIO_FIELD, "font-mono tabular-nums read-only:cursor-not-allowed")}
            {...form.register("approval_expiry_days", { valueAsNumber: true })}
          />
          <p id={`${ids}-expiry-hint`} className={STUDIO_HINT}>
            {t("expiry.description", { min, max })}
          </p>
          {expiryError && <FieldError id={`${ids}-expiry-error`}>{expiryError}</FieldError>}
        </div>

        {state.saveError && <StudioInlineError error={state.saveError} title={t("saveFailed")} />}

        {canEdit && (
          <div className="flex flex-wrap items-center gap-2">
            <ShimmerButton type="submit" disabled={!state.isDirty || state.isSaving}>
              <SaveIcon aria-hidden />
              {state.isSaving ? t("saving") : t("save")}
            </ShimmerButton>
            <button
              type="button"
              disabled={!state.isDirty || state.isSaving}
              onClick={() => {
                form.reset();
                state.clearSaveError();
              }}
              className={cn(GHOST_BUTTON, "h-10 disabled:opacity-50")}
            >
              {t("discard")}
            </button>
            {state.isDirty && <p className="text-xs text-muted-foreground">{t("unsaved")}</p>}
          </div>
        )}
      </form>
    </StudioPanel>
  );
}
