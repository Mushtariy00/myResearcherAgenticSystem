"use client";

import { AlertCircleIcon, InfoIcon, LockIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useId } from "react";
import { Controller } from "react-hook-form";
import { toast } from "sonner";
import type { Privacy } from "@/client";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { useErrorMessage } from "@/hooks/use-error-message";
import {
  PROJECT_SETTINGS_LIMITS,
  projectSettingsFieldError,
  useProjectSettings,
} from "@/hooks/use-project-settings";

const PRIVACY_LEVELS: readonly Privacy[] = ["standard", "confidential"];

function isPrivacy(value: unknown): value is Privacy {
  return typeof value === "string" && (PRIVACY_LEVELS as readonly string[]).includes(value);
}

/** A labelled switch row; the whole row toggles it, the description is read after the name. */
function SwitchRow({
  id,
  label,
  description,
  children,
  control,
}: {
  id: string;
  label: string;
  description: string;
  children?: ReactNode;
  control: (props: { "aria-labelledby": string; "aria-describedby": string }) => ReactNode;
}) {
  return (
    <div className="grid gap-2 rounded-lg border p-3">
      <Label className="flex cursor-pointer items-start justify-between gap-4 font-normal leading-normal has-data-readonly:cursor-default">
        <span className="grid gap-1">
          <span id={`${id}-label`} className="font-medium">
            {label}
          </span>
          <span id={`${id}-description`} className="text-xs leading-snug text-muted-foreground">
            {description}
          </span>
        </span>
        {control({
          "aria-labelledby": `${id}-label`,
          "aria-describedby": `${id}-description`,
        })}
      </Label>
      {children}
    </div>
  );
}

/**
 * A project's settings. Owners and lab admins change and save them; everyone else reads them
 * (the controls are read-only, and nothing offers to save).
 */
export function SettingsPanel({ projectId, canEdit }: { projectId: string; canEdit: boolean }) {
  const t = useTranslations("project.settings");
  const tAll = useTranslations();
  const errorMessage = useErrorMessage();
  const ids = useId();
  const settings = useProjectSettings(projectId);
  const { form } = settings;
  const readOnly = !canEdit;
  const saving = settings.isSaving;
  const limits = PROJECT_SETTINGS_LIMITS.approvalExpiryDays;

  if (settings.query.isPending) {
    return <LoadingRows rows={4} />;
  }
  if (settings.query.isError) {
    return <QueryError error={settings.query.error} onRetry={() => settings.query.refetch()} />;
  }

  const expiryError = projectSettingsFieldError(form.formState.errors.approval_expiry_days);
  const privacyError = projectSettingsFieldError(form.formState.errors.privacy);

  // Every field at once, on top of the latest settings; the result says whether it was saved.
  const save = form.handleSubmit(async (values) => {
    const result = await settings.update(values);
    if (result.ok) {
      toast.success(t("saved"));
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2>{t("title")}</h2>
        </CardTitle>
        <CardDescription>{canEdit ? t("description") : t("descriptionReadOnly")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={save} className="grid gap-6" noValidate>
          {readOnly && (
            <p className="flex items-start gap-2 rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
              <LockIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
              {t("readOnly")}
            </p>
          )}
          {settings.saveError && (
            <Alert variant="destructive">
              <AlertCircleIcon aria-hidden />
              <AlertDescription>{errorMessage(settings.saveError)}</AlertDescription>
            </Alert>
          )}

          <fieldset className="grid gap-3">
            <legend id={`${ids}-privacy`} className="mb-1 text-sm font-medium">
              {t("privacy.label")}
            </legend>
            <Controller
              control={form.control}
              name="privacy"
              render={({ field }) => (
                <RadioGroup
                  aria-labelledby={`${ids}-privacy`}
                  value={field.value}
                  onValueChange={(value) => {
                    if (isPrivacy(value)) {
                      field.onChange(value);
                    }
                  }}
                  readOnly={readOnly}
                  disabled={saving}
                  className="grid gap-2 sm:grid-cols-2"
                >
                  {PRIVACY_LEVELS.map((value) => (
                    <Label
                      key={value}
                      className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal leading-normal has-data-checked:border-primary has-data-checked:bg-muted/50 has-data-readonly:cursor-default"
                    >
                      {/* Base UI renders the radio as a span, so name it explicitly. */}
                      <RadioGroupItem
                        value={value}
                        className="mt-0.5"
                        aria-labelledby={`${ids}-${value}-label`}
                        aria-describedby={`${ids}-${value}-description`}
                      />
                      <span className="grid gap-1">
                        <span id={`${ids}-${value}-label`} className="font-medium">
                          {t(`privacy.${value}.label`)}
                        </span>
                        <span
                          id={`${ids}-${value}-description`}
                          className="text-xs leading-snug text-muted-foreground"
                        >
                          {t(`privacy.${value}.description`)}
                        </span>
                      </span>
                    </Label>
                  ))}
                </RadioGroup>
              )}
            />
            {privacyError && (
              <p className="text-sm text-destructive">
                {tAll(privacyError.key, privacyError.values)}
              </p>
            )}
          </fieldset>

          <div className="grid gap-3">
            <Controller
              control={form.control}
              name="allow_free_models"
              render={({ field }) => (
                <SwitchRow
                  id={`${ids}-free`}
                  label={t("allowFreeModels.label")}
                  description={t("allowFreeModels.description")}
                  control={(labels) => (
                    <Switch
                      {...labels}
                      checked={field.value}
                      onCheckedChange={field.onChange}
                      readOnly={readOnly}
                      disabled={saving}
                    />
                  )}
                />
              )}
            />
            <Controller
              control={form.control}
              name="auto_approve"
              render={({ field }) => (
                <SwitchRow
                  id={`${ids}-auto`}
                  label={t("autoApprove.label")}
                  description={t("autoApprove.description")}
                  control={(labels) => (
                    <Switch
                      {...labels}
                      checked={field.value}
                      onCheckedChange={field.onChange}
                      readOnly={readOnly}
                      disabled={saving}
                    />
                  )}
                >
                  <p className="flex items-start gap-2 text-xs text-muted-foreground">
                    <InfoIcon aria-hidden className="mt-px size-3.5 shrink-0" />
                    {t("autoApprove.codingNote")}
                  </p>
                </SwitchRow>
              )}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor={`${ids}-expiry`}>{t("expiry.label")}</Label>
            <div className="flex items-center gap-2">
              <Input
                id={`${ids}-expiry`}
                type="number"
                inputMode="numeric"
                min={limits.min}
                max={limits.max}
                step={1}
                readOnly={readOnly || saving}
                aria-invalid={expiryError ? true : undefined}
                aria-describedby={`${ids}-expiry-hint${expiryError ? ` ${ids}-expiry-error` : ""}`}
                className="w-24"
                {...form.register("approval_expiry_days", { valueAsNumber: true })}
              />
              <span className="text-sm text-muted-foreground">{t("expiry.unit")}</span>
            </div>
            <p id={`${ids}-expiry-hint`} className="text-xs text-muted-foreground">
              {t("expiry.hint", limits)}
            </p>
            {expiryError && (
              <p id={`${ids}-expiry-error`} className="text-sm text-destructive">
                {tAll(expiryError.key, expiryError.values)}
              </p>
            )}
          </div>

          {canEdit && (
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={!settings.isDirty || saving}>
                {saving ? t("saving") : t("save")}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={!settings.isDirty || saving}
                onClick={() => {
                  settings.clearSaveError();
                  form.reset(settings.settings, { keepDirtyValues: false });
                }}
              >
                {t("discard")}
              </Button>
            </div>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
