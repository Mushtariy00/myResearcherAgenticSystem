"use client";

import {
  CircleCheckIcon,
  CircleXIcon,
  FileCode2Icon,
  FolderTreeIcon,
  GitCompareArrowsIcon,
  PlayIcon,
  TestTubeDiagonalIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";
import type { CodingOutput } from "@/client";
import { CodeBlock } from "@/components/shared/code-block";
import { CodeDiff } from "@/components/shared/code-diff";
import { CodeViewer } from "@/components/shared/code-viewer";
import { countLines, diffCodeFiles } from "@/components/shared/diff-files";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import { useRunPage } from "./run-context";
import { entrypointFile } from "./run-helpers";
import { Chip, TOGGLE_BUTTON, ViewCard } from "./run-ui";

/** The version a coding output is compared with. */
export type CodingBase = {
  data: CodingOutput;
  relation: "version" | "attempt";
  attempt: number;
  version: number;
};

/**
 * The coding output: what was built and its entry point, the smoke test with its log, the
 * changes since the previous attempt (or version) as a code diff, and every generated file in
 * the code viewer, with the code archive to download when it belongs to the version on screen.
 */
export function CodingView({
  data,
  outputId,
  previous,
}: {
  data: CodingOutput;
  outputId: string;
  previous: CodingBase | null;
}) {
  const t = useTranslations("studioRun.coding");
  const format = useFormatter();
  const { runId } = useRunPage();
  const { codeArchive } = useRunArtifacts(runId);
  const archive = codeArchive?.stage_output_id === outputId ? codeArchive : undefined;
  const lines = data.files.reduce((total, file) => total + countLines(file.content), 0);
  const smoke = data.smoke_test;

  return (
    <div className="grid min-w-0 gap-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <ViewCard title={t("summary")} icon={<FileCode2Icon aria-hidden />}>
          <div className="grid gap-4">
            <p className="text-sm leading-6 break-words whitespace-pre-line text-foreground">
              {data.summary}
            </p>
            <dl className="flex flex-wrap gap-2">
              <div>
                <dt className="sr-only">{t("entrypoint")}</dt>
                <dd>
                  <Chip stage="coding" mono title={t("entrypoint")}>
                    <PlayIcon aria-hidden />
                    {data.entrypoint}
                  </Chip>
                </dd>
              </div>
              <div>
                <dt className="sr-only">{t("code")}</dt>
                <dd>
                  <Chip>
                    {t("filesLines", {
                      files: data.files.length,
                      lines: format.number(lines),
                    })}
                  </Chip>
                </dd>
              </div>
            </dl>
          </div>
        </ViewCard>
        <ViewCard
          title={t("smokeTest")}
          icon={<TestTubeDiagonalIcon aria-hidden />}
          action={
            <Chip tone={smoke.passed ? "success" : "danger"}>
              {smoke.passed ? <CircleCheckIcon aria-hidden /> : <CircleXIcon aria-hidden />}
              {smoke.passed ? t("passed") : t("failed")}
            </Chip>
          }
        >
          <div className="grid gap-2">
            <p className="text-xs text-muted-foreground tabular-nums">
              {t("duration", {
                seconds: format.number(smoke.duration_seconds, { maximumFractionDigits: 1 }),
              })}
            </p>
            <div className="overflow-hidden rounded-lg border bg-card">
              <CodeBlock code={smoke.log} language="bash" label={t("log")} maxHeight="14rem" />
            </div>
          </div>
        </ViewCard>
      </div>

      {previous && <CodeChanges before={previous} after={data} />}

      <ViewCard title={t("code")} icon={<FolderTreeIcon aria-hidden />}>
        <CodeViewer
          files={data.files}
          defaultPath={entrypointFile(data.entrypoint)}
          downloadUrl={archive ? artifactUrl(archive.id) : undefined}
          downloadFilename={archive?.filename}
        />
      </ViewCard>
    </div>
  );
}

function CodeChanges({ before, after }: { before: CodingBase; after: CodingOutput }) {
  const t = useTranslations("studioRun.coding");
  const tDiff = useTranslations("shared.diff");
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const summary = useMemo(() => {
    const changed = diffCodeFiles(before.data.files, after.files).filter(
      (change) => change.status !== "unchanged",
    );
    return {
      files: changed.length,
      additions: changed.reduce((total, change) => total + change.additions, 0),
      deletions: changed.reduce((total, change) => total + change.deletions, 0),
    };
  }, [before.data.files, after.files]);

  return (
    <ViewCard
      title={
        before.relation === "attempt"
          ? t("changesSinceAttempt", { attempt: before.attempt })
          : t("changesSinceVersion", { version: before.version })
      }
      icon={<GitCompareArrowsIcon aria-hidden />}
      description={
        <span className="flex flex-wrap items-center gap-2 tabular-nums">
          <span>{tDiff("summary", { count: summary.files })}</span>
          <span aria-hidden>
            <span data-tone="success" className="text-(--tone-fg)">
              +{summary.additions}
            </span>{" "}
            <span data-tone="danger" className="text-(--tone-fg)">
              −{summary.deletions}
            </span>
          </span>
          <span className="sr-only">
            {tDiff("lineCounts", { additions: summary.additions, deletions: summary.deletions })}
          </span>
        </span>
      }
      action={
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className={TOGGLE_BUTTON}
        >
          {open ? t("hideChanges") : t("showChanges")}
        </button>
      }
    >
      <div id={panelId} hidden={!open}>
        {open && <CodeDiff before={before.data.files} after={after.files} height="28rem" />}
      </div>
    </ViewCard>
  );
}
