"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCallback } from "react";

/** Why a source could not be searched (agentic_scholarly SourceError codes). */
const SOURCE_ERRORS = [
  "source.rate_limited",
  "source.quota_exhausted",
  "source.http_status",
  "source.network",
  "source.bad_response",
] as const;

const SOURCES = ["arxiv", "semantic_scholar", "openalex", "crossref", "core", "demo"] as const;

type Params = Record<string, unknown>;

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function texts(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : null;
}

function member<T extends string>(list: readonly T[], value: unknown): value is T {
  return typeof value === "string" && (list as readonly string[]).includes(value);
}

/**
 * The progress lines of the real LLM stages (apps/worker: literature/progress.py and the method
 * and writing runners), worded once for both interfaces. Returns null for any other code, or
 * when the params don't fit the code; the caller then shows the worker's English message.
 */
export function useStageLogLine(): (code: string, p: Params) => string | null {
  const t = useTranslations("shared.stageLog");
  const tSources = useTranslations("shared.papers.sources");
  const format = useFormatter();

  return useCallback(
    (code: string, p: Params): string | null => {
      const source = (id: string) => (member(SOURCES, id) ? tSources(id) : id);
      switch (code) {
        case "literature.searched": {
          const sources = texts(p.sources);
          const queries = count(p.queries);
          const found = count(p.found);
          const incomplete = count(p.incomplete) ?? 0;
          if (!sources || queries === null || found === null) {
            return null;
          }
          const values = {
            sources: format.list(sources.map(source), { type: "conjunction" }),
            queries,
            found,
            incomplete,
          };
          return incomplete > 0
            ? t("literature.searchedIncomplete", values)
            : t("literature.searched", values);
        }
        case "literature.source_failed": {
          if (typeof p.source !== "string" || !member(SOURCE_ERRORS, p.error)) {
            return null;
          }
          const error = p.error.slice("source.".length) as SourceError;
          const reason = t(`literature.sourceErrors.${error}`);
          return t("literature.sourceFailed", { source: source(p.source), reason });
        }
        case "literature.screened": {
          const candidates = count(p.candidates);
          const included = count(p.included);
          return candidates !== null && included !== null
            ? t("literature.screened", { candidates, included })
            : null;
        }
        case "literature.fetched": {
          const pdfs = count(p.pdfs);
          const abstractOnly = count(p.abstract_only);
          if (pdfs === null || abstractOnly === null) {
            return null;
          }
          return abstractOnly > 0
            ? t("literature.fetched", { pdfs, abstractOnly })
            : t("literature.fetchedAll", { pdfs });
        }
        case "literature.parsed":
        case "literature.analyzed": {
          const papers = count(p.papers);
          const key = code === "literature.parsed" ? "literature.parsed" : "literature.analyzed";
          return papers !== null ? t(key, { papers }) : null;
        }
        case "literature.synthesized": {
          const findings = count(p.findings);
          return findings !== null ? t("literature.synthesized", { findings }) : null;
        }
        case "method.proposed": {
          const proposals = count(p.proposals);
          const gaps = count(p.gaps);
          return proposals !== null && gaps !== null
            ? t("method.proposed", { proposals, gaps })
            : null;
        }
        case "writing.outlined": {
          const sections = count(p.sections);
          return sections !== null ? t("writing.outlined", { sections }) : null;
        }
        case "writing.drafted": {
          const section = text(p.section);
          const index = count(p.index);
          const sections = count(p.sections);
          return section && index !== null && sections !== null
            ? t("writing.drafted", { section, index, sections })
            : null;
        }
        case "writing.cited": {
          const citations = count(p.citations);
          const removed = count(p.removed) ?? 0;
          if (citations === null) {
            return null;
          }
          return removed > 0
            ? t("writing.citedRemoved", { citations, removed })
            : t("writing.cited", { citations });
        }
        default:
          return null;
      }
    },
    [t, tSources, format],
  );
}

type SourceError = (typeof SOURCE_ERRORS)[number] extends `source.${infer Name}` ? Name : never;
