"use client";

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { lineChanges } from "./diff-files";
import { toJsonText } from "./json-parse";
import { UnifiedDiff } from "./unified-diff";

export type JsonDiffProps = {
  /** The output as produced (e.g. the version under review). */
  before: unknown;
  /** The edited or newer value. */
  after: unknown;
  /** Accessible name of the diff region; default "Changes". */
  label?: string;
  /** Compare with object keys sorted, so reordered keys are not reported (default true). */
  sortKeys?: boolean;
  /** Unchanged lines around each change; default 3. */
  context?: number;
  maxHeight?: string;
  className?: string;
};

/** A line diff of two JSON values, pretty-printed, for approve-with-edits. */
export function JsonDiff({
  before,
  after,
  label,
  sortKeys = true,
  context = 3,
  maxHeight = "28rem",
  className,
}: JsonDiffProps) {
  const t = useTranslations("shared.json");
  const tDiff = useTranslations("shared.diff");
  const [left, right] = useMemo(
    () => [toJsonText(before, { sortKeys }), toJsonText(after, { sortKeys })],
    [before, after, sortKeys],
  );
  const counts = useMemo(() => lineChanges(left, right), [left, right]);
  const unchanged = left === right;
  return (
    <div data-slot="json-diff" className={cn("grid gap-2", className)}>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {unchanged ? (
          t("noChanges")
        ) : (
          <>
            <span aria-hidden className="tabular-nums">
              <span data-tone="success" className="text-(--tone-fg)">
                +{counts.additions}
              </span>{" "}
              <span data-tone="danger" className="text-(--tone-fg)">
                −{counts.deletions}
              </span>
            </span>
            <span className="sr-only">{tDiff("lineCounts", counts)}</span>
          </>
        )}
      </p>
      {!unchanged && (
        <UnifiedDiff
          before={left}
          after={right}
          context={context}
          label={label ?? t("changes")}
          maxHeight={maxHeight}
          className="rounded-lg border bg-card"
        />
      )}
    </div>
  );
}
