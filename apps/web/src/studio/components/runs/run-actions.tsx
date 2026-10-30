"use client";

import { Menu } from "@base-ui/react/menu";
import {
  ChevronDownIcon,
  DownloadIcon,
  FileArchiveIcon,
  FileCodeIcon,
  FileTextIcon,
  FlaskConicalIcon,
  type LucideIcon,
  RotateCcwIcon,
  SquareIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import type { ArtifactOut } from "@/client";
import { formatBytes } from "@/components/shared/format";
import { StageDot } from "@/components/shared/stage-icon";
import { useCancelRun } from "@/hooks/use-cancel-run";
import { useErrorMessage } from "@/hooks/use-error-message";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import { compareStages } from "@/lib/stage-meta";
import { cn } from "@/lib/utils";
import { StudioConfirmDialog } from "./confirm-dialog";
import { useRunPage } from "./run-context";
import { ACTION_BUTTON, Chip } from "./run-ui";
import { useRunLabels } from "./use-run-labels";

const KIND_ICONS: Record<ArtifactOut["kind"], LucideIcon> = {
  code_file: FileCodeIcon,
  code_archive: FileArchiveIcon,
  experiment_log: FileTextIcon,
  metrics: FileTextIcon,
  draft: FileTextIcon,
  references: FileTextIcon,
};

/** The run's actions in the header: downloads, retry (finished runs), cancel (unfinished). */
export function RunActions() {
  const { view, openRetry } = useRunPage();
  const t = useTranslations("studioRun");
  const canRetry = view.finished && view.retryableStages.length > 0;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <DownloadsMenu />
      {canRetry && (
        <button
          type="button"
          className={ACTION_BUTTON}
          aria-haspopup="dialog"
          onClick={() => openRetry()}
        >
          <RotateCcwIcon aria-hidden />
          {t("retry.button")}
        </button>
      )}
      {view.canCancel && <CancelRunAction />}
    </div>
  );
}

/** Cancel the run, after a confirmation (work in progress stops; money spent stays spent). */
function CancelRunAction() {
  const { runId } = useRunPage();
  const t = useTranslations("run.cancel");
  const errorMessage = useErrorMessage();
  const [open, setOpen] = useState(false);
  const cancel = useCancelRun({
    onCancelled: () => toast.success(t("requested")),
    onAlreadyFinished: (_runId, error) => toast.info(errorMessage(error)),
    onError: (error) => toast.error(errorMessage(error)),
  });
  return (
    <>
      <button
        type="button"
        className={cn(ACTION_BUTTON, "text-(--studio-danger-fg)")}
        aria-haspopup="dialog"
        disabled={cancel.pending}
        onClick={() => setOpen(true)}
      >
        <SquareIcon aria-hidden />
        {cancel.pending ? t("cancelling") : t("button")}
      </button>
      <StudioConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={t("confirmTitle")}
        description={t("confirmDescription")}
        confirmLabel={t("confirm")}
        cancelLabel={t("keepRunning")}
        onConfirm={() => {
          setOpen(false);
          cancel.cancel(runId);
        }}
      />
    </>
  );
}

/** Every file the run's latest outputs make, grouped by stage, as download links in a menu. */
function DownloadsMenu() {
  const { runId } = useRunPage();
  const t = useTranslations("studioRun.downloads");
  const format = useFormatter();
  const labels = useRunLabels();
  const files = useRunArtifacts(runId);
  if (files.artifacts.length === 0) {
    return null;
  }
  const groups = Object.entries(files.byStage).sort(([a], [b]) => compareStages(a, b));

  return (
    <Menu.Root>
      <Menu.Trigger className={ACTION_BUTTON}>
        <DownloadIcon aria-hidden />
        {t("button")}
        <span className="text-xs text-muted-foreground tabular-nums">
          {format.number(files.artifacts.length)}
        </span>
        <ChevronDownIcon aria-hidden className="text-muted-foreground" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="bottom" align="end" sideOffset={8} className="isolate z-50">
          <Menu.Popup
            className={cn(
              "studio-glass max-h-[min(28rem,var(--available-height))] w-[min(22rem,calc(100vw-2rem))] origin-(--transform-origin) overflow-y-auto rounded-2xl bg-popover p-1.5 text-popover-foreground outline-none",
              "transition-[scale,opacity] duration-150 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0 motion-reduce:transition-none",
            )}
          >
            {files.demo && (
              <div className="px-2 pt-1.5 pb-1">
                <Chip tone="warning">
                  <FlaskConicalIcon aria-hidden />
                  {t("demo")}
                </Chip>
              </div>
            )}
            {groups.map(([stage, items]) => (
              <Menu.Group key={stage} className="py-1">
                <Menu.GroupLabel className="flex items-center gap-2 px-2 pt-1.5 pb-1 text-xs font-semibold text-muted-foreground">
                  <StageDot stage={stage} />
                  {labels.stage(stage)}
                </Menu.GroupLabel>
                {items.map((artifact) => {
                  const Icon = KIND_ICONS[artifact.kind] ?? FileTextIcon;
                  return (
                    <Menu.LinkItem
                      key={artifact.id}
                      href={artifactUrl(artifact.id)}
                      download={artifact.filename}
                      closeOnClick
                      className="flex min-w-0 items-center gap-3 rounded-[10px] px-2 py-1.5 text-sm text-foreground outline-none select-none data-highlighted:bg-(--studio-hover)"
                    >
                      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                      <span className="grid min-w-0 flex-1">
                        <span className="truncate font-medium">{artifact.filename}</span>
                        <span className="truncate text-xs text-muted-foreground">
                          {t(`kinds.${artifact.kind}`)} · {formatBytes(artifact.size_bytes, format)}
                        </span>
                      </span>
                    </Menu.LinkItem>
                  );
                })}
              </Menu.Group>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
