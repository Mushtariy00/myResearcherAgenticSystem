"use client";

import {
  DownloadIcon,
  FileTextIcon,
  ListTreeIcon,
  PenLineIcon,
  QuoteIcon,
  TargetIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useMemo } from "react";
import type { WritingOutput } from "@/client";
import { formatBytes } from "@/components/shared/format";
import { MarkdownDraft } from "@/components/shared/markdown-draft";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import { countWords } from "@/lib/stage-output";
import { cn } from "@/lib/utils";
import { NumberTicker } from "@/studio/components/effects/number-ticker";
import { useRunPage } from "./run-context";
import { Callout, LINK_BUTTON, SMALL_BUTTON, ViewCard } from "./run-ui";

/**
 * The writing output: the title, abstract and review focus with the draft's numbers, the draft
 * itself (table of contents; each `[n]` citation opens the citation sheet), its outline, the
 * references and the files to download for the version on screen.
 */
export function WritingView({ data, outputId }: { data: WritingOutput; outputId: string }) {
  const t = useTranslations("studioRun.writing");
  const format = useFormatter();
  const { runId, literature, openPaper } = useRunPage();
  const { byStage } = useRunArtifacts(runId);
  const files = (byStage.writing ?? []).filter((file) => file.stage_output_id === outputId);
  const words = useMemo(() => countWords(data.markdown), [data.markdown]);
  const citations = data.citations ?? [];
  const papers = literature?.papers;
  const byId = useMemo(
    () => new Map((papers ?? []).map((paper) => [paper.paper_id, paper])),
    [papers],
  );

  const stats = [
    { key: "words", value: words },
    { key: "sections", value: data.sections.length },
    { key: "citations", value: citations.length },
  ] as const;

  return (
    <div className="grid min-w-0 gap-4">
      <ViewCard
        title={data.title}
        icon={<FileTextIcon aria-hidden />}
        description={data.output_format}
      >
        <div className="grid gap-4">
          <dl className="grid grid-cols-3 gap-3">
            {stats.map((stat) => (
              <div
                key={stat.key}
                className="grid min-w-0 gap-1 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-3"
              >
                <dt className="truncate text-xs text-muted-foreground">{t(`stats.${stat.key}`)}</dt>
                <dd className="font-mono text-xl font-semibold tracking-tight text-foreground">
                  <NumberTicker value={stat.value} />
                </dd>
              </div>
            ))}
          </dl>
          <div className="grid gap-1.5">
            <h5 className="text-[0.7rem] font-semibold tracking-[0.08em] text-muted-foreground uppercase">
              {t("abstract")}
            </h5>
            <p className="text-sm leading-7 break-words text-foreground">{data.abstract}</p>
          </div>
          <Callout tone="info" icon={TargetIcon} title={t("reviewFocus")}>
            {data.review_focus}
          </Callout>
        </div>
      </ViewCard>

      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_20rem] 2xl:items-start">
        <ViewCard title={t("draft")} icon={<PenLineIcon aria-hidden />}>
          {/* The draft's table of contents sticks below the Studio top bar, not under it. */}
          <div className="[&_nav]:top-20">
            <MarkdownDraft
              markdown={data.markdown}
              citations={citations}
              papers={papers}
              onCite={(key, paper) =>
                openPaper({ paperId: paper?.paper_id ?? null, citationKey: key })
              }
              idPrefix="draft-"
            />
          </div>
        </ViewCard>

        <div className="grid min-w-0 content-start gap-4">
          <ViewCard title={t("outline")} icon={<ListTreeIcon aria-hidden />}>
            <ol className="grid gap-2.5">
              {data.sections.map((section, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: section names may repeat; the list never reorders
                <li key={index} className="grid gap-0.5">
                  <span className="text-sm font-medium break-words text-foreground">
                    <span className="mr-1.5 font-mono text-xs text-(--tone-fg) tabular-nums">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {section.name}
                  </span>
                  <span className="text-xs break-words text-muted-foreground">
                    {section.objective}
                  </span>
                </li>
              ))}
            </ol>
          </ViewCard>

          <ViewCard title={t("references")} icon={<QuoteIcon aria-hidden />}>
            {citations.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noReferences")}</p>
            ) : (
              <ol className="grid gap-2">
                {citations.map((citation) => {
                  const paper = byId.get(citation.paper_id);
                  return (
                    <li key={citation.key} className="flex min-w-0 gap-2 text-sm">
                      <span className="shrink-0 font-mono text-xs leading-5 text-(--tone-fg) tabular-nums">
                        [{citation.key}]
                      </span>
                      <button
                        type="button"
                        aria-haspopup="dialog"
                        onClick={() =>
                          openPaper({ paperId: citation.paper_id, citationKey: citation.key })
                        }
                        className={cn(LINK_BUTTON, "min-w-0 text-left break-words text-foreground")}
                      >
                        {paper
                          ? t("reference", { title: paper.title, year: paper.year })
                          : citation.paper_id}
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </ViewCard>

          <ViewCard title={t("downloads")} icon={<DownloadIcon aria-hidden />}>
            {files.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noDownloads")}</p>
            ) : (
              <ul className="grid gap-2">
                {files.map((file) => (
                  <li key={file.id}>
                    <a
                      href={artifactUrl(file.id)}
                      download={file.filename}
                      className={cn(SMALL_BUTTON, "w-full justify-start")}
                    >
                      <DownloadIcon aria-hidden />
                      <span className="min-w-0 truncate">{file.filename}</span>
                      <span className="ml-auto font-normal text-muted-foreground tabular-nums">
                        {formatBytes(file.size_bytes, format)}
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </ViewCard>
        </div>
      </div>
    </div>
  );
}
