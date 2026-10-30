"use client";

import { Menu } from "@base-ui/react/menu";
import { ChevronDownIcon, DownloadIcon, FlaskConicalIcon, RotateCwIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ArtifactOut } from "@/client";
import { formatBytes } from "@/components/shared/format";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useErrorMessage } from "@/hooks/use-error-message";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import { useLabels } from "./use-labels";

/** Menu order and wording of each kind of artifact. */
const KINDS: readonly ArtifactOut["kind"][] = [
  "code_archive",
  "code_file",
  "experiment_log",
  "metrics",
  "draft",
  "references",
];

function DownloadItem({ artifact }: { artifact: ArtifactOut }) {
  const t = useTranslations("run.downloads");
  const format = useFormatter();
  const label =
    artifact.kind === "code_file"
      ? (artifact.path ?? artifact.filename)
      : t(`kinds.${artifact.kind}`);
  return (
    <Menu.LinkItem
      href={artifactUrl(artifact.id)}
      download={artifact.filename}
      closeOnClick
      label={label}
      className="flex cursor-default items-center gap-2 rounded-md px-1.5 py-1 text-sm outline-hidden select-none focus:bg-accent focus:text-accent-foreground data-highlighted:bg-accent data-highlighted:text-accent-foreground"
    >
      <DownloadIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
        {formatBytes(artifact.size_bytes, format)}
      </span>
    </Menu.LinkItem>
  );
}

/**
 * Every file the run's latest outputs make (useRunArtifacts), grouped by stage: the code (all
 * of it as a zip, or file by file), the training log and metrics, the draft and its references.
 */
export function DownloadsMenu({ runId }: { runId: string }) {
  const t = useTranslations("run.downloads");
  const tDemo = useTranslations("shared.demo");
  const labels = useLabels();
  const errorMessage = useErrorMessage();
  const { query, byStage, demo } = useRunArtifacts(runId);
  const stages = Object.keys(byStage);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="outline">
            <DownloadIcon aria-hidden />
            {t("button")}
            <ChevronDownIcon aria-hidden />
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-80 max-w-[calc(100vw-2rem)]">
        {query.isPending ? (
          <p className="px-1.5 py-2 text-sm text-muted-foreground">{t("loading")}</p>
        ) : query.isError ? (
          <>
            <p className="px-1.5 py-2 text-sm text-destructive">{errorMessage(query.error)}</p>
            <DropdownMenuItem closeOnClick={false} onClick={() => query.refetch()}>
              <RotateCwIcon aria-hidden />
              {t("retry")}
            </DropdownMenuItem>
          </>
        ) : stages.length === 0 ? (
          <p className="px-1.5 py-2 text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <>
            {demo && (
              // The Demo badge is a popover trigger, which a menu cannot hold: say it in text.
              <p
                data-tone="warning"
                className="mb-1 flex items-start gap-1.5 rounded-md bg-(--tone)/10 px-1.5 py-1 text-xs text-(--tone-fg)"
              >
                <FlaskConicalIcon aria-hidden className="mt-px size-3.5 shrink-0" />
                <span>
                  <span className="font-medium">{tDemo("title")}:</span> {tDemo("description")}
                </span>
              </p>
            )}
            {stages.map((stage, index) => {
              const items = [...(byStage[stage] ?? [])].sort(
                (a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind),
              );
              return (
                <DropdownMenuGroup key={stage}>
                  {index > 0 && <DropdownMenuSeparator />}
                  <DropdownMenuLabel>{labels.stage(stage)}</DropdownMenuLabel>
                  {items.map((artifact) => (
                    <DownloadItem key={artifact.id} artifact={artifact} />
                  ))}
                </DropdownMenuGroup>
              );
            })}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
