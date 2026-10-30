"use client";

import { CircleAlertIcon, RotateCcwIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { RunDetail, Stage } from "@/client";
import { StageStatusBadge } from "@/components/app/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useRetryRun } from "@/hooks/use-retry-run";
import type { StageOverview } from "@/lib/stage-output";
import { suggestedRetryStage } from "./run-data";
import { useLabels } from "./use-labels";

/**
 * Runs a finished run again from a stage the reviewer picks (useRetryRun). The dialog says what
 * a retry does: the chosen stage and every later one start over, and their current outputs
 * become outdated, while the approved outputs before it are kept.
 */
export function RetryRunDialog({
  run,
  stages,
  timeline,
}: {
  run: Pick<RunDetail, "id" | "config">;
  /** The stages a retry may start from (`useRunView().retryableStages`). */
  stages: readonly Stage[];
  timeline: readonly StageOverview[];
}) {
  const t = useTranslations("run.retry");
  const tc = useTranslations("common");
  const labels = useLabels();
  const format = useFormatter();
  const errorMessage = useErrorMessage();
  const ids = useId();
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<string | null>(null);
  const retry = useRetryRun({
    onRetried: (_runId, stage) => {
      toast.success(t("started", { stage: labels.stage(stage) }));
      setOpen(false);
    },
  });

  const selected = stages.find((stage) => stage === choice) ?? null;
  const order = run.config.stages;
  const start = selected ? order.indexOf(selected) : -1;
  const affected = start >= 0 ? order.slice(start) : [];
  const statusOf = (stage: string) => timeline.find((entry) => entry.stage === stage)?.status;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          // Each opening starts from where the run stopped, without the last failure.
          setChoice(suggestedRetryStage(timeline, stages));
          retry.reset();
        }
      }}
    >
      <DialogTrigger
        render={
          <Button variant="outline">
            <RotateCcwIcon aria-hidden />
            {t("button")}
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <p id={`${ids}-label`} className="text-sm font-medium">
            {t("stageLabel")}
          </p>
          <RadioGroup
            aria-labelledby={`${ids}-label`}
            value={selected}
            onValueChange={(value) => setChoice(String(value))}
            className="grid gap-2"
          >
            {stages.map((stage) => {
              const status = statusOf(stage);
              return (
                <Label
                  key={stage}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border p-3 font-normal has-data-checked:border-primary has-data-checked:bg-muted/50"
                >
                  {/* Base UI renders the radio as a span, so name it explicitly for screen readers. */}
                  <RadioGroupItem value={stage} aria-labelledby={`${ids}-${stage}`} />
                  <span id={`${ids}-${stage}`} className="flex-1 font-medium">
                    {labels.stage(stage)}
                  </span>
                  {status && <StageStatusBadge status={status} />}
                </Label>
              );
            })}
          </RadioGroup>
        </div>
        <div className="grid gap-2 text-sm" aria-live="polite">
          {selected ? (
            <p>
              {t("affected", {
                stages: format.list(affected.map((stage) => labels.stage(stage))),
              })}
            </p>
          ) : (
            <p className="text-muted-foreground">{t("choose")}</p>
          )}
          <p className="text-xs text-muted-foreground">{t("keepNote")}</p>
          <p className="text-xs text-muted-foreground">{t("costNote")}</p>
        </div>
        {retry.error && (
          <Alert variant="destructive">
            <CircleAlertIcon aria-hidden />
            <AlertDescription>{errorMessage(retry.error)}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>{tc("cancel")}</DialogClose>
          <Button
            disabled={!selected || retry.pending}
            onClick={() => {
              if (selected) {
                retry.retry(run.id, selected);
              }
            }}
          >
            <RotateCcwIcon aria-hidden />
            {retry.pending
              ? t("retrying")
              : selected
                ? t("confirm", { stage: labels.stage(selected) })
                : t("confirmEmpty")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
