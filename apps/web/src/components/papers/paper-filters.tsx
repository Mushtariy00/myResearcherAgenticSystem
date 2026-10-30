"use client";

import { SearchIcon, XIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PAPER_SEARCH } from "@/hooks/use-paper-search";
import {
  hasPaperFilters,
  isPaperSource,
  isScreeningDecision,
  NO_PAPER_FILTERS,
  PAPER_SOURCES,
  type PaperFilters,
  SCREENING_DECISIONS,
} from "./library";

/** The select value for "no filter" (Base UI selects show their placeholder for null). */
const ANY = "any";

export type PaperFilterBarProps = {
  value: PaperFilters;
  onChange: (next: PaperFilters) => void;
  /** A year is not a whole number in 1900..2100, or the first is after the second. */
  yearRangeInvalid: boolean;
};

/** Search text, year range, screening decision and source of the paper library. */
export function PaperFilterBar({ value, onChange, yearRangeInvalid }: PaperFilterBarProps) {
  const t = useTranslations("papers.filters");
  const tPapers = useTranslations("shared.papers");
  const ids = useId();
  const set = (patch: Partial<PaperFilters>) => onChange({ ...value, ...patch });
  const yearsErrorId = `${ids}-years-error`;

  const decisionItems = {
    [ANY]: t("anyDecision"),
    ...Object.fromEntries(
      SCREENING_DECISIONS.map((decision) => [decision, tPapers(`decisions.${decision}`)]),
    ),
  };
  const sourceItems = {
    [ANY]: t("anySource"),
    ...Object.fromEntries(PAPER_SOURCES.map((source) => [source, tPapers(`sources.${source}`)])),
  };

  // Filters apply as they change, so there is nothing to submit: a search landmark, not a form.
  return (
    <search aria-label={t("label")} className="grid gap-3">
      <div className="relative">
        <Label htmlFor={`${ids}-q`} className="sr-only">
          {t("search")}
        </Label>
        <SearchIcon
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          id={`${ids}-q`}
          type="search"
          value={value.q}
          onChange={(event) => set({ q: event.target.value })}
          placeholder={t("searchPlaceholder")}
          maxLength={PAPER_SEARCH.maxQueryLength}
          autoComplete="off"
          className="pl-8"
        />
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-from`}>{t("yearFrom")}</Label>
          <Input
            id={`${ids}-from`}
            type="number"
            inputMode="numeric"
            min={PAPER_SEARCH.minYear}
            max={PAPER_SEARCH.maxYear}
            step={1}
            value={value.yearFrom}
            onChange={(event) => set({ yearFrom: event.target.value })}
            aria-invalid={yearRangeInvalid || undefined}
            aria-describedby={yearRangeInvalid ? yearsErrorId : undefined}
            className="w-28"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor={`${ids}-to`}>{t("yearTo")}</Label>
          <Input
            id={`${ids}-to`}
            type="number"
            inputMode="numeric"
            min={PAPER_SEARCH.minYear}
            max={PAPER_SEARCH.maxYear}
            step={1}
            value={value.yearTo}
            onChange={(event) => set({ yearTo: event.target.value })}
            aria-invalid={yearRangeInvalid || undefined}
            aria-describedby={yearRangeInvalid ? yearsErrorId : undefined}
            className="w-28"
          />
        </div>
        <div className="grid gap-1.5">
          <Label id={`${ids}-decision`}>{t("decision")}</Label>
          <Select
            items={decisionItems}
            value={value.decision ?? ANY}
            onValueChange={(next) => set({ decision: isScreeningDecision(next) ? next : null })}
          >
            <SelectTrigger className="w-40" aria-labelledby={`${ids}-decision`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(decisionItems).map(([item, label]) => (
                <SelectItem key={item} value={item}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label id={`${ids}-source`}>{t("source")}</Label>
          <Select
            items={sourceItems}
            value={value.source ?? ANY}
            onValueChange={(next) => set({ source: isPaperSource(next) ? next : null })}
          >
            <SelectTrigger className="w-44" aria-labelledby={`${ids}-source`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(sourceItems).map(([item, label]) => (
                <SelectItem key={item} value={item}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {hasPaperFilters(value) && (
          <Button type="button" variant="ghost" onClick={() => onChange({ ...NO_PAPER_FILTERS })}>
            <XIcon aria-hidden />
            {t("clear")}
          </Button>
        )}
      </div>
      {yearRangeInvalid && (
        <p id={yearsErrorId} role="alert" className="text-sm text-destructive">
          {t("yearRangeInvalid", { min: PAPER_SEARCH.minYear, max: PAPER_SEARCH.maxYear })}
        </p>
      )}
    </search>
  );
}
