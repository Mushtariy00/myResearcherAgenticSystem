"use client";

import { structuredPatch } from "diff";
import { useTranslations } from "next-intl";
import { Fragment, useMemo } from "react";
import { cn } from "@/lib/utils";
import { countLines, normalizeText } from "./diff-files";

type DiffRow =
  | { kind: "hunk"; header: string; skipped: number }
  | { kind: "context" | "added" | "removed"; text: string; oldLine?: number; newLine?: number }
  | { kind: "note"; text: string };

/** Rows of a unified diff with old and new line numbers, and the unchanged lines between hunks. */
export function unifiedDiffRows(before: string, after: string, context = 3): DiffRow[] {
  const patch = structuredPatch(
    "before",
    "after",
    normalizeText(before),
    normalizeText(after),
    "",
    "",
    {
      context,
    },
  );
  const rows: DiffRow[] = [];
  let previousEnd = 1;
  for (const hunk of patch.hunks) {
    rows.push({
      kind: "hunk",
      header: `@@ -${hunk.oldStart},${hunk.oldLines} +${hunk.newStart},${hunk.newLines} @@`,
      skipped: Math.max(0, hunk.oldStart - previousEnd),
    });
    let oldLine = hunk.oldStart;
    let newLine = hunk.newStart;
    for (const line of hunk.lines) {
      const marker = line[0];
      const text = line.slice(1);
      if (marker === "+") {
        rows.push({ kind: "added", text, newLine });
        newLine += 1;
      } else if (marker === "-") {
        rows.push({ kind: "removed", text, oldLine });
        oldLine += 1;
      } else if (marker === "\\") {
        rows.push({ kind: "note", text: line });
      } else {
        rows.push({ kind: "context", text, oldLine, newLine });
        oldLine += 1;
        newLine += 1;
      }
    }
    previousEnd = hunk.oldStart + hunk.oldLines;
  }
  const trailing = countLines(before) - (previousEnd - 1);
  if (rows.length > 0 && trailing > 0) {
    rows.push({ kind: "hunk", header: "", skipped: trailing });
  }
  return rows;
}

export type UnifiedDiffProps = {
  before: string;
  after: string;
  /** Accessible name of the scrollable diff region. */
  label: string;
  /** Unchanged lines kept around each change; default 3. */
  context?: number;
  maxHeight?: string;
  className?: string;
};

/**
 * A lightweight unified diff (no editor): hunks with old and new line numbers, `+`/`−` markers
 * and colour, and the changed text inside ins/del so assistive technology reports it.
 */
export function UnifiedDiff({
  before,
  after,
  label,
  context = 3,
  maxHeight,
  className,
}: UnifiedDiffProps) {
  const t = useTranslations("shared.diff");
  const rows = useMemo(() => unifiedDiffRows(before, after, context), [before, after, context]);
  if (rows.length === 0) {
    return <p className={cn("p-4 text-sm text-muted-foreground", className)}>{t("noChanges")}</p>;
  }
  return (
    <section
      aria-label={label}
      data-slot="unified-diff"
      // biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users must be able to scroll it
      tabIndex={0}
      className={cn(
        "overflow-auto font-mono text-xs leading-5 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset",
        className,
      )}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <div className="grid w-max min-w-full py-1">
        {rows.map((row, index) => {
          const key = `${index}`;
          if (row.kind === "hunk") {
            return (
              <Fragment key={key}>
                {row.skipped > 0 && (
                  <div className="px-3 py-0.5 text-muted-foreground italic">
                    {t("skipped", { count: row.skipped })}
                  </div>
                )}
                {row.header && (
                  <div className="bg-muted/60 px-3 py-0.5 text-muted-foreground">{row.header}</div>
                )}
              </Fragment>
            );
          }
          if (row.kind === "note") {
            return (
              <div key={key} className="px-3 text-muted-foreground italic">
                {row.text}
              </div>
            );
          }
          const tone =
            row.kind === "added" ? "success" : row.kind === "removed" ? "danger" : undefined;
          const marker = row.kind === "added" ? "+" : row.kind === "removed" ? "−" : " ";
          const Text = row.kind === "added" ? "ins" : row.kind === "removed" ? "del" : "span";
          return (
            <div
              key={key}
              data-tone={tone}
              data-line={row.kind}
              className={cn("grid grid-cols-[3.5rem_3.5rem_1.5rem_1fr]", tone && "bg-(--tone)/12")}
            >
              <span
                aria-hidden
                className="pr-2 text-right text-muted-foreground tabular-nums select-none"
              >
                {row.oldLine ?? ""}
              </span>
              <span
                aria-hidden
                className="pr-2 text-right text-muted-foreground tabular-nums select-none"
              >
                {row.newLine ?? ""}
              </span>
              <span
                aria-hidden
                className={cn("text-center select-none", tone && "font-semibold text-(--tone-fg)")}
              >
                {marker}
              </span>
              <Text className="pr-4 whitespace-pre no-underline">{row.text || " "}</Text>
            </div>
          );
        })}
      </div>
    </section>
  );
}
