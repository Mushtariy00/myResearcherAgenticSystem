"use client";

import { ClipboardCheckIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { LiteratureOutput, WritingOutput } from "@/client";
import { DownloadLink } from "@/components/shared/download-link";
import { MarkdownDraft } from "@/components/shared/markdown-draft";
import { artifactUrl, useRunArtifacts } from "@/hooks/use-run-artifacts";
import { PaperSheet, usePaperSheet } from "../paper-sheet";
import { artifactsOf } from "../run-data";
import { Prose, ViewSection } from "./view-section";

/**
 * A writing output: the title and abstract, the draft (with a table of contents and citation
 * buttons that open the cited paper), the planned sections, what reviewers should check, and
 * the draft and references downloads when they were made from this version.
 */
export function WritingView({
  runId,
  outputId,
  data,
  literature,
}: {
  runId: string;
  outputId: string;
  data: WritingOutput;
  /** The literature output the citations point into. */
  literature: LiteratureOutput | null;
}) {
  const t = useTranslations("run.writing");
  const sheet = usePaperSheet();
  const { artifacts } = useRunArtifacts(runId);
  const own = artifactsOf(artifacts, outputId);
  const draft = own.find((artifact) => artifact.kind === "draft");
  const references = own.find((artifact) => artifact.kind === "references");
  const papers = literature?.papers ?? [];

  return (
    <div className="grid gap-6">
      <div className="grid gap-1">
        <h3 className="text-xl font-semibold tracking-tight break-words">{data.title}</h3>
        {data.output_format && (
          <p className="text-xs text-muted-foreground">
            {t("format", { format: data.output_format })}
          </p>
        )}
      </div>
      <ViewSection title={t("abstract")}>
        <Prose text={data.abstract} />
      </ViewSection>
      <ViewSection
        title={t("draft")}
        actions={
          (draft || references) && (
            <div className="flex flex-wrap gap-2">
              {draft && (
                <DownloadLink
                  href={artifactUrl(draft.id)}
                  filename={draft.filename}
                  sizeBytes={draft.size_bytes}
                >
                  {t("downloadDraft")}
                </DownloadLink>
              )}
              {references && (
                <DownloadLink
                  href={artifactUrl(references.id)}
                  filename={references.filename}
                  sizeBytes={references.size_bytes}
                >
                  {t("downloadReferences")}
                </DownloadLink>
              )}
            </div>
          )
        }
      >
        <div className="rounded-xl border p-4 sm:p-6">
          <MarkdownDraft
            markdown={data.markdown}
            citations={data.citations}
            papers={papers}
            onCite={(_key, paper) => {
              if (paper) {
                sheet.show(paper.paper_id);
              }
            }}
            idPrefix="draft-"
          />
        </div>
      </ViewSection>
      <div className="grid gap-6 lg:grid-cols-2">
        <ViewSection title={t("sections")}>
          {data.sections.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("noSections")}</p>
          ) : (
            <ol className="grid list-decimal gap-2 pl-5">
              {data.sections.map((section, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: sections are positional
                <li key={index} className="break-words">
                  <span className="font-medium">{section.name}</span>
                  <span className="block text-muted-foreground">{section.objective}</span>
                </li>
              ))}
            </ol>
          )}
        </ViewSection>
        <ViewSection title={t("reviewFocus")}>
          <div className="flex items-start gap-2 rounded-xl border bg-muted/30 p-3">
            <ClipboardCheckIcon aria-hidden className="mt-0.5 size-4 shrink-0" />
            <Prose text={data.review_focus} />
          </div>
        </ViewSection>
      </div>
      <PaperSheet sheet={sheet} papers={papers} analyses={literature?.analyses} />
    </div>
  );
}
