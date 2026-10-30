"use client";

import { useTranslations } from "next-intl";
import { useId, useMemo, useState } from "react";
import { DemoBadge } from "@/components/shared/demo-badge";
import { PapersTable } from "@/components/shared/papers-table";
import { type ScreeningDecision, usePaperSearch } from "@/hooks/use-paper-search";
import { cn } from "@/lib/utils";
import { StudioSearchInput, StudioSelect } from "@/studio/components/dashboard/studio-fields";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { toPaperRef } from "@/studio/components/papers/library";
import { Pager } from "@/studio/components/papers/pager";
import { glassClassName } from "@/studio/lib/glass";
import { PaperSheet } from "./paper-sheet";

const DECISIONS = ["include", "maybe", "exclude"] as const satisfies readonly ScreeningDecision[];

function isDecision(value: string): value is ScreeningDecision {
  return (DECISIONS as readonly string[]).includes(value);
}

/**
 * The papers the project's runs found (usePaperSearch, filtered to the project): search as you
 * type, a screening filter, the shared papers table (sortable, keyboard-selectable rows), and a
 * sheet with the paper's PDF and analyses for the chosen row.
 */
export function ProjectPapersTab({ projectId }: { projectId: string }) {
  const t = useTranslations("studioWork.project.papers");
  const tPapers = useTranslations("studioWork.papers");
  const tDecisions = useTranslations("shared.papers.decisions");
  const ids = useId();
  const [q, setQ] = useState("");
  const [decision, setDecision] = useState<ScreeningDecision | "">("");
  const [open, setOpen] = useState<{ id: string; title: string } | null>(null);
  const search = usePaperSearch({ q, projectId, decision: decision || null });
  const papers = useMemo(() => search.items.map(toPaperRef), [search.items]);
  const loading = search.query.isPending && !search.query.isError;

  return (
    <div className="grid gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="grid min-w-0 flex-1 gap-1.5">
          <label htmlFor={`${ids}-q`} className="text-xs font-medium text-muted-foreground">
            {tPapers("search")}
          </label>
          <StudioSearchInput
            id={`${ids}-q`}
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder={tPapers("searchPlaceholder")}
            autoComplete="off"
          />
        </div>
        <div className="grid gap-1.5 sm:w-48">
          <label htmlFor={`${ids}-decision`} className="text-xs font-medium text-muted-foreground">
            {tPapers("filters.decision")}
          </label>
          <StudioSelect
            id={`${ids}-decision`}
            value={decision}
            onChange={(event) =>
              setDecision(isDecision(event.target.value) ? event.target.value : "")
            }
          >
            <option value="">{tPapers("filters.anyDecision")}</option>
            {DECISIONS.map((value) => (
              <option key={value} value={value}>
                {tDecisions(value)}
              </option>
            ))}
          </StudioSelect>
        </div>
      </div>

      <div className="flex min-h-6 flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <p role="status" className="tabular-nums">
          {search.isSearching ? (
            <span className="inline-flex items-center gap-1.5">
              <PulseDot tone="info" live size="sm" />
              {tPapers("searching")}
            </span>
          ) : search.query.isSuccess ? (
            tPapers("results", { count: search.total })
          ) : null}
        </p>
        <DemoBadge demo={search.demo} />
      </div>

      {search.query.isError ? (
        <StudioInlineError error={search.query.error} onRetry={() => search.query.refetch()} />
      ) : (
        <div className={cn(glassClassName(), "min-w-0 overflow-hidden px-1 sm:px-2")}>
          <PapersTable
            papers={papers}
            loading={loading}
            selectedId={open?.id ?? null}
            onSelect={(paper) => setOpen({ id: paper.paper_id, title: paper.title })}
            caption={t("caption")}
            emptyMessage={q || decision ? tPapers("noMatch") : t("empty")}
          />
        </div>
      )}
      <Pager search={search} label={tPapers("pager.label")} />
      <PaperSheet
        paper={open}
        onOpenChange={(next) => {
          if (!next) {
            setOpen(null);
          }
        }}
      />
    </div>
  );
}
