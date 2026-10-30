"use client";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { ArrowUpRightIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { LoadingRows, QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { usePaper } from "@/hooks/use-paper";
import { PaperByline, PaperDetailBody } from "./paper-detail-body";
import { paperHref } from "./paper-href";

export type PaperSheetProps = {
  /** The paper to show; null closes the sheet. */
  paperId: string | null;
  onClose: () => void;
};

/**
 * A paper from a table, in a sheet on the right: its record, abstract, analyses with evidence
 * in the PDF, and the runs that found it, with a link to its own page. Focus stays inside while
 * it is open and returns to the row that opened it; Escape closes it.
 */
export function PaperSheet({ paperId, onClose }: PaperSheetProps) {
  const t = useTranslations("papers.sheet");
  const tc = useTranslations("common");
  // The last paper stays on screen while the sheet slides out.
  const [shownId, setShownId] = useState(paperId);
  if (paperId !== null && paperId !== shownId) {
    setShownId(paperId);
  }
  const paper = usePaper(shownId);

  return (
    <DialogPrimitive.Root
      open={paperId !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 isolate z-50 bg-black/10 duration-150 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup
          data-slot="paper-sheet"
          className="fixed inset-y-0 right-0 z-50 flex h-dvh w-full flex-col bg-popover text-sm text-popover-foreground shadow-lg ring-1 ring-foreground/10 duration-200 outline-none sm:max-w-2xl data-open:animate-in data-open:slide-in-from-right data-closed:animate-out data-closed:slide-out-to-right motion-reduce:animate-none"
        >
          <div className="flex items-start gap-3 border-b px-4 py-3">
            <div className="grid min-w-0 flex-1 gap-1">
              <DialogPrimitive.Title className="text-base leading-snug font-medium break-words">
                {paper.data?.paper.title ?? t("title")}
              </DialogPrimitive.Title>
              {paper.data && (
                <DialogPrimitive.Description className="text-sm text-muted-foreground">
                  <PaperByline paper={paper.data.paper} />
                </DialogPrimitive.Description>
              )}
              {paper.data && shownId && (
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Link
                    href={paperHref(shownId)}
                    className={buttonVariants({ variant: "outline", size: "sm" })}
                  >
                    <ArrowUpRightIcon aria-hidden />
                    {t("openPage")}
                  </Link>
                  <DemoBadge demo={paper.data.demo} />
                </div>
              )}
            </div>
            <DialogPrimitive.Close
              render={<Button variant="ghost" size="icon-sm" className="shrink-0" />}
            >
              <XIcon aria-hidden />
              <span className="sr-only">{tc("close")}</span>
            </DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4">
            {paper.isPending ? (
              <LoadingRows rows={4} label={t("loading")} />
            ) : paper.isError ? (
              <QueryError error={paper.error} onRetry={() => paper.refetch()} />
            ) : (
              <PaperDetailBody detail={paper.data} layout="sheet" />
            )}
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
