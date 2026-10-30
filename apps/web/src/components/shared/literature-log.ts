"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useCallback } from "react";

/** Codes of the real literature stage's progress lines (apps/worker literature/progress.py). */
export const LITERATURE_LOG_CODES = [
  "literature.searched",
  "literature.source_failed",
  "literature.screened",
  "literature.fetched",
  "literature.parsed",
  "literature.analyzed",
  "literature.synthesized",
] as const;

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

function texts(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : null;
}

function member<T extends string>(list: readonly T[], value: unknown): value is T {
  return typeof value === "string" && (list as readonly string[]).includes(value);
}

/**
 * The literature stage's progress lines, worded once for both interfaces. Returns null for any
 * other code, or when the params don't fit the code; the caller then shows the worker's English
 * message.
 */
export function useLiteratureLogLine(): (code: string, p: Params) => string | null {
  const t = useTranslations("shared.literatureLog");
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
          return incomplete > 0 ? t("searchedIncomplete", values) : t("searched", values);
        }
        case "literature.source_failed": {
          if (typeof p.source !== "string" || !member(SOURCE_ERRORS, p.error)) {
            return null;
          }
          const reason = t(`sourceErrors.${p.error.slice("source.".length) as SourceError}`);
          return t("sourceFailed", { source: source(p.source), reason });
        }
        case "literature.screened": {
          const candidates = count(p.candidates);
          const included = count(p.included);
          return candidates !== null && included !== null
            ? t("screened", { candidates, included })
            : null;
        }
        case "literature.fetched": {
          const pdfs = count(p.pdfs);
          const abstractOnly = count(p.abstract_only);
          if (pdfs === null || abstractOnly === null) {
            return null;
          }
          return abstractOnly > 0
            ? t("fetched", { pdfs, abstractOnly })
            : t("fetchedAll", { pdfs });
        }
        case "literature.parsed":
        case "literature.analyzed": {
          const papers = count(p.papers);
          const key = code === "literature.parsed" ? "parsed" : "analyzed";
          return papers !== null ? t(key, { papers }) : null;
        }
        case "literature.synthesized": {
          const findings = count(p.findings);
          return findings !== null ? t("synthesized", { findings }) : null;
        }
        default:
          return null;
      }
    },
    [t, tSources, format],
  );
}

type SourceError = (typeof SOURCE_ERRORS)[number] extends `source.${infer Name}` ? Name : never;
