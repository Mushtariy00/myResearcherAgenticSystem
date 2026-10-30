"use client";

import { Dialog } from "@base-ui/react/dialog";
import { CircleAlertIcon, HistoryIcon, RotateCcwIcon, XIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { toast } from "sonner";
import { StageIcon } from "@/components/shared/stage-icon";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useRetryRun } from "@/hooks/use-retry-run";
import { cn } from "@/lib/utils";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { stageAttr } from "@/studio/lib/stages";
import { ICON_BUTTON, OUTLINE_BUTTON } from "@/studio/lib/ui";
import { STUDIO_BACKDROP } from "./confirm-dialog";
import { useRunPage } from "./run-context";
import { Callout, StageStatusChip } from "./run-ui";
import { useRunLabels } from "./use-run-labels";

type DialogState = { open: boolean; stage: string | null };

/**
 * Runs a finished run again from a stage the visitor picks among the run's retryable stages
 * (useRetryRun). It says what happens: approved outputs before that stage stay, and that stage
 * and the ones after it run again, so their current outputs become outdated (they stay readable
 * as earlier versions). Refusals from the API are shown in the dialog.
 */
export function RetryRunDialog({
  open,
  initialStage,
  onOpenChange,
}: {
  open: boolean;
  /** The stage to suggest; default the last one the run reached. */
  initialStage: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { runId, view, showStage } = useRunPage();
  const t = useTranslations("studioRun.retry");
  const format = useFormatter();
  const labels = useRunLabels();
  const errorMessage = useErrorMessage();
  const name = useId();
  const retryable = view.retryableStages;

  const [state, setState] = useState<DialogState>({ open: false, stage: null });
  let selected = state.stage;
  if (state.open !== open) {
    // Each opening starts from the suggested stage.
    const suggested =
      initialStage && (retryable as readonly string[]).includes(initialStage)
        ? initialStage
        : (retryable.at(-1) ?? null);
    selected = open ? suggested : state.stage;
    setState({ open, stage: selected });
  }

  const retry = useRetryRun({
    onRetried: (_runId, stage) => {
      toast.success(t("started", { stage: labels.stage(stage) }));
      onOpenChange(false);
      showStage(stage);
    },
  });

  function changeOpen(next: boolean) {
    if (!next) {
      retry.reset();
    }
    onOpenChange(next);
  }

  const index = selected ? view.timeline.findIndex((entry) => entry.stage === selected) : -1;
  const before = index > 0 ? view.timeline[index - 1] : undefined;
  const outdated =
    index >= 0
      ? view.timeline
          .slice(index)
          .filter((entry) => entry.attempts > 0)
          .map((entry) => labels.stage(entry.stage))
      : [];
  const outdatedText =
    outdated.length === 0
      ? null
      : t(outdated.length === 1 ? "outdatedOne" : "outdatedMany", {
          stages: format.list(outdated, { type: "conjunction" }),
        });

  return (
    <Dialog.Root open={open} onOpenChange={changeOpen}>
      <Dialog.Portal>
        <Dialog.Backdrop className={STUDIO_BACKDROP} />
        <Dialog.Popup
          className={cn(
            "studio-glass fixed top-[max(1rem,8vh)] left-1/2 z-50 grid max-h-[calc(100dvh-2rem)] w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 content-start gap-5 overflow-y-auto overscroll-contain rounded-2xl bg-popover p-5 text-popover-foreground outline-none sm:p-6",
            "transition-[scale,opacity] duration-200 ease-out data-ending-style:scale-[0.98] data-ending-style:opacity-0 data-starting-style:scale-[0.98] data-starting-style:opacity-0 motion-reduce:transition-none",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="grid min-w-0 gap-1.5">
              <Dialog.Title className="flex items-center gap-2 text-lg font-semibold tracking-tight text-foreground">
                <RotateCcwIcon aria-hidden className="size-4.5 text-(--studio-accent-fg)" />
                {t("title")}
              </Dialog.Title>
              <Dialog.Description className="text-sm text-pretty text-muted-foreground">
                {t("description")}
              </Dialog.Description>
            </div>
            <Dialog.Close aria-label={t("close")} className={cn(ICON_BUTTON, "-mt-1 -mr-1")}>
              <XIcon aria-hidden />
            </Dialog.Close>
          </div>

          <fieldset className="grid min-w-0 gap-2">
            <legend className="mb-2 text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
              {t("stages")}
            </legend>
            {retryable.map((stage) => {
              const entry = view.timeline.find((item) => item.stage === stage);
              return (
                <label
                  key={stage}
                  data-stage={stageAttr(stage)}
                  className="flex cursor-pointer items-center gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3 transition-colors hover:bg-(--studio-hover) has-checked:border-(--tone)/50 has-checked:bg-(--tone)/10 has-focus-visible:ring-3 has-focus-visible:ring-ring/50 motion-reduce:transition-none"
                >
                  <input
                    type="radio"
                    name={name}
                    value={stage}
                    checked={selected === stage}
                    onChange={() => setState({ open, stage })}
                    className="size-4 shrink-0 accent-[var(--tone)] outline-none"
                  />
                  <span
                    aria-hidden
                    className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-(--tone)/30 bg-(--tone)/12"
                  >
                    <StageIcon stage={stage} />
                  </span>
                  <span className="grid min-w-0 flex-1">
                    <span className="truncate text-sm font-medium text-foreground">
                      {labels.stage(stage)}
                    </span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {t("attempts", { count: entry?.attempts ?? 0 })}
                    </span>
                  </span>
                  {entry && <StageStatusChip status={entry.status} />}
                </label>
              );
            })}
          </fieldset>

          {selected && (
            <Callout tone="warning" icon={HistoryIcon} title={t("consequences")}>
              <ul className="grid list-disc gap-1 pl-4">
                <li>
                  {before ? t("keeps", { stage: labels.stage(selected) }) : t("keepsNothing")}
                </li>
                {outdatedText && <li>{outdatedText}</li>}
                <li>{t("cost")}</li>
              </ul>
            </Callout>
          )}

          {retry.error && (
            <Callout tone="danger" icon={CircleAlertIcon} role="alert" title={t("failed")}>
              {errorMessage(retry.error)}
            </Callout>
          )}

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Dialog.Close className={OUTLINE_BUTTON}>{t("cancel")}</Dialog.Close>
            <ShimmerButton
              disabled={!selected || retry.pending}
              onClick={() => {
                if (selected) {
                  retry.retry(runId, selected);
                }
              }}
            >
              <RotateCcwIcon aria-hidden />
              {retry.pending
                ? t("starting")
                : t("confirm", { stage: selected ? labels.stage(selected) : "" })}
            </ShimmerButton>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
