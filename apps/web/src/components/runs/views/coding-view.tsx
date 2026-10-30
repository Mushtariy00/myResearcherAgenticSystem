"use client";

import { CircleCheckIcon, CircleXIcon, GitCompareIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import type { CodeFile, CodingOutput } from "@/client";
import { CodeBlock } from "@/components/shared/code-block";
import { CodeDiff } from "@/components/shared/code-diff";
import { CodeViewer } from "@/components/shared/code-viewer";
import { Button } from "@/components/ui/button";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import { entrypointFile } from "../run-data";
import { Prose, ViewSection } from "./view-section";

/** The coding output a version is compared with (see `DiffBase`). */
export type CodingBase = {
  relation: "version" | "attempt";
  attempt: number;
  version: number;
  files: readonly CodeFile[];
};

/**
 * A coding output: the summary, the entrypoint, the smoke test with its log, the generated
 * files (with the code archive when it was made from this version), and a comparison with the
 * version or attempt before it.
 */
export function CodingView({
  runId,
  outputId,
  data,
  previous,
}: {
  runId: string;
  outputId: string;
  data: CodingOutput;
  previous?: CodingBase | null;
}) {
  const t = useTranslations("run.coding");
  const format = useFormatter();
  const compareId = useId();
  const [comparing, setComparing] = useState(false);
  const { codeArchive } = useRunArtifacts(runId);
  // Artifacts follow the stage's latest output; an older version has no archive of its own.
  const archive = codeArchive?.stage_output_id === outputId ? codeArchive : undefined;
  const smoke = data.smoke_test;
  const compareLabel =
    previous?.relation === "version"
      ? t("compareVersion", { version: previous.version })
      : t("compareAttempt", { attempt: previous?.attempt ?? 0 });

  return (
    <div className="grid gap-6">
      <ViewSection title={t("summary")}>
        <Prose text={data.summary} />
        <p className="text-sm">
          <span className="text-muted-foreground">{t("entrypoint")}</span>{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs break-all">
            {data.entrypoint}
          </code>
        </p>
      </ViewSection>
      <ViewSection
        title={t("smokeTest")}
        actions={
          <span
            data-tone={smoke.passed ? "success" : "danger"}
            className="inline-flex h-6 items-center gap-1.5 rounded-full bg-(--tone)/15 px-2.5 text-xs font-medium text-(--tone-fg)"
          >
            {smoke.passed ? (
              <CircleCheckIcon aria-hidden className="size-3.5" />
            ) : (
              <CircleXIcon aria-hidden className="size-3.5" />
            )}
            {smoke.passed ? t("passed") : t("failed")}
            <span className="font-normal tabular-nums">
              ·{" "}
              {format.number(smoke.duration_seconds, {
                style: "unit",
                unit: "second",
                unitDisplay: "short",
                maximumFractionDigits: 1,
              })}
            </span>
          </span>
        }
      >
        {smoke.log.trim() ? (
          <CodeBlock
            code={smoke.log}
            label={t("smokeLog")}
            maxHeight="16rem"
            className="rounded-lg border bg-muted/30"
          />
        ) : (
          <p className="text-sm text-muted-foreground">{t("noLog")}</p>
        )}
      </ViewSection>
      <ViewSection title={t("files", { count: data.files.length })}>
        <CodeViewer
          files={data.files}
          defaultPath={entrypointFile(data.entrypoint)}
          downloadUrl={archive ? artifactUrl(archive.id) : undefined}
          downloadFilename={archive?.filename}
        />
      </ViewSection>
      {previous && (
        <ViewSection
          title={t("compare")}
          actions={
            <Button
              variant="outline"
              size="sm"
              aria-expanded={comparing}
              aria-controls={compareId}
              onClick={() => setComparing((open) => !open)}
            >
              <GitCompareIcon aria-hidden />
              {comparing ? t("hideCompare") : compareLabel}
            </Button>
          }
        >
          <div id={compareId}>
            {comparing && <CodeDiff before={previous.files} after={data.files} />}
          </div>
        </ViewSection>
      )}
    </div>
  );
}
