"use client";

import { CheckIcon, EyeIcon, PencilIcon, RotateCcwIcon, XIcon } from "lucide-react";
import { LayoutGroup, motion } from "motion/react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import type { VersionRef } from "@/lib/stage-output";
import { SPRING } from "@/studio/lib/motion";

/**
 * Every version of every attempt of a stage, oldest first, as a row of toggle buttons with a
 * sliding indicator. Markers say which version is under review, which a reviewer edited, and
 * what was decided on each. The row scrolls sideways when it does not fit (the indicator's
 * layout animation measures that scroll: `layoutScroll`).
 */
export function VersionSwitcher({
  versions,
  selectedId,
  reviewId,
  onSelect,
}: {
  versions: readonly VersionRef[];
  selectedId: string | null;
  /** The version waiting for review, if it is one of these. */
  reviewId: string | null;
  onSelect: (outputId: string) => void;
}) {
  const t = useTranslations("studioRun.stage");
  const group = useId();
  return (
    <fieldset className="max-w-full min-w-0">
      <legend className="sr-only">{t("versions")}</legend>
      <LayoutGroup id={group}>
        <motion.div
          layoutScroll
          className="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) p-1"
        >
          {versions.map(({ attempt, output }) => {
            const selected = output.id === selectedId;
            const reviewing = output.id === reviewId;
            const decision = output.approval?.decision;
            const notes = [
              reviewing ? t("underReview") : null,
              decision === "approve" ? t("approved") : null,
              decision === "request_changes" ? t("changesRequested") : null,
              decision === "reject" ? t("rejected") : null,
              output.edited_by ? t("editedMark") : null,
            ].filter(Boolean);
            const label = [
              t("versionLabel", { attempt: attempt.attempt, version: output.version }),
              ...notes,
            ].join(", ");
            return (
              <button
                key={output.id}
                type="button"
                aria-pressed={selected}
                aria-label={label}
                title={label}
                onClick={() => onSelect(output.id)}
                className="relative inline-flex h-7 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium whitespace-nowrap text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:text-foreground motion-reduce:transition-none"
              >
                {selected && (
                  <motion.span
                    layoutId="version-indicator"
                    transition={SPRING}
                    aria-hidden
                    className="absolute inset-0 rounded-lg border border-(--tone)/40 bg-(--tone)/14"
                  />
                )}
                <span aria-hidden className="relative z-10 inline-flex items-center gap-1.5">
                  <span className="tabular-nums">
                    {t("versionShort", { attempt: attempt.attempt, version: output.version })}
                  </span>
                  {reviewing && <EyeIcon className="size-3.5 text-(--studio-warning-fg)" />}
                  {decision === "approve" && (
                    <CheckIcon className="size-3.5 text-(--studio-success-fg)" />
                  )}
                  {decision === "request_changes" && (
                    <RotateCcwIcon className="size-3.5 text-(--studio-warning-fg)" />
                  )}
                  {decision === "reject" && (
                    <XIcon className="size-3.5 text-(--studio-danger-fg)" />
                  )}
                  {output.edited_by && <PencilIcon className="size-3 text-muted-foreground" />}
                </span>
              </button>
            );
          })}
        </motion.div>
      </LayoutGroup>
    </fieldset>
  );
}
