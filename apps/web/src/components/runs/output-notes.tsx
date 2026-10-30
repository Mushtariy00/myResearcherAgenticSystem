"use client";

import { FlaskConicalIcon, TriangleAlertIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { StageOutputOut } from "@/client";
import { DemoBadge } from "@/components/shared/demo-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { isDemoOutput } from "@/lib/stage-output";
import { useLabels } from "./use-labels";

type NotedOutput = Pick<StageOutputOut, "degraded" | "degraded_reason">;

/**
 * A degraded output that is not demo data: a fallback or partial placeholder the reviewer must
 * check. Demo outputs get the Demo badge and `DemoNotice` instead.
 */
export function DegradedWarning({ output }: { output: NotedOutput }) {
  const t = useTranslations("run.approval");
  const labels = useLabels();
  if (!output.degraded || isDemoOutput(output)) {
    return null;
  }
  return (
    <Alert variant="destructive">
      <TriangleAlertIcon aria-hidden />
      <AlertTitle>{t("degradedTitle")}</AlertTitle>
      <AlertDescription>
        <p>{t("degradedDescription")}</p>
        {output.degraded_reason && (
          <p className="mt-1">
            {t("degradedReason")}{" "}
            <span className="break-words">{labels.degradedReason(output.degraded_reason)}</span>
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}

/** Says that an output under review is generated demo data, and why. */
export function DemoNotice({ output }: { output: NotedOutput }) {
  const t = useTranslations("run.approval");
  const labels = useLabels();
  if (!isDemoOutput(output)) {
    return null;
  }
  return (
    <Alert role="note">
      <FlaskConicalIcon aria-hidden />
      <AlertTitle>{t("demoTitle")}</AlertTitle>
      <AlertDescription>
        {output.degraded_reason
          ? `${t("demoDescription")} ${t("degradedReason")} ${labels.degradedReason(output.degraded_reason)}`
          : t("demoDescription")}
      </AlertDescription>
    </Alert>
  );
}

/**
 * Attempt, version, model, time, editor and hash of an output, with the Demo badge for demo
 * data.
 */
export function OutputMeta({
  output,
  attempt,
  editedBy,
}: {
  output: StageOutputOut;
  /** The attempt the output belongs to, once the stage detail says. */
  attempt?: number;
  /** Who edited this version (approve with edits); a name, or "" when unknown. */
  editedBy?: string | null;
}) {
  const t = useTranslations("run.approval");
  const tVersions = useTranslations("run.versions");
  const format = useFormatter();
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
      <dl className="flex flex-wrap gap-x-6 gap-y-1">
        {attempt !== undefined && (
          <div className="flex gap-1">
            <dt>{tVersions("attempt")}</dt>
            <dd className="font-medium text-foreground tabular-nums">{attempt}</dd>
          </div>
        )}
        {editedBy !== undefined && editedBy !== null && (
          <div className="flex gap-1">
            <dt>{tVersions("edited")}</dt>
            <dd className="font-medium text-foreground">{editedBy || tVersions("someone")}</dd>
          </div>
        )}
        <div className="flex gap-1">
          <dt>{t("version")}</dt>
          <dd className="font-medium text-foreground tabular-nums">{output.version}</dd>
        </div>
        <div className="flex gap-1">
          <dt>{t("model")}</dt>
          <dd className="font-medium text-foreground">{output.model ?? t("unknownModel")}</dd>
        </div>
        <div className="flex gap-1">
          <dt>{t("produced")}</dt>
          <dd className="font-medium text-foreground">
            {format.dateTime(new Date(output.created_at), {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </dd>
        </div>
        <div className="flex min-w-0 gap-1">
          <dt>{t("hash")}</dt>
          <dd className="truncate font-mono" title={output.sha256}>
            {output.sha256.slice(0, 12)}
          </dd>
        </div>
      </dl>
      <DemoBadge demo={isDemoOutput(output)} degradedReason={output.degraded_reason} />
    </div>
  );
}
