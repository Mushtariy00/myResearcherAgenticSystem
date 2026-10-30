"use client";

import { Dialog } from "@base-ui/react/dialog";
import { ArrowUpRightIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { STUDIO_BACKDROP } from "@/studio/components/dashboard/create-project-dialog";
import { PaperDetailContent } from "@/studio/components/papers/paper-detail-content";
import { studioPaperPath } from "@/studio/lib/nav";
import { GHOST_BUTTON, ICON_BUTTON } from "@/studio/lib/ui";

/**
 * A paper of the project in a glass sheet from the end edge: its PDF (with the evidence
 * highlighted), the analyses and the runs that found it, without leaving the project. A modal
 * dialog (focus stays inside; Escape and the backdrop close it), with a link to the paper's own
 * page. Full width on phones.
 */
export function PaperSheet({
  paper,
  onOpenChange,
}: {
  /** The paper to show (id and title, known from the list); null when closed. */
  paper: { id: string; title: string } | null;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("studioWork.project.papers");
  const tCommon = useTranslations("common");
  // The closing sheet keeps showing its paper while it slides out.
  const [last, setLast] = useState(paper);
  if (paper && paper !== last) {
    setLast(paper);
  }
  const shown = paper ?? last;

  return (
    <Dialog.Root open={paper !== null} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className={STUDIO_BACKDROP} />
        <Dialog.Popup
          className={cn(
            "studio-glass studio-blur fixed inset-y-0 right-0 z-50 flex w-[min(52rem,100vw)] flex-col rounded-none border-y-0 border-r-0 bg-(--studio-glass-strong) text-foreground outline-none sm:rounded-l-2xl",
            "transition-[translate] duration-300 ease-out data-ending-style:translate-x-full data-starting-style:translate-x-full motion-reduce:transition-none",
          )}
        >
          <div className="flex items-start justify-between gap-3 border-b border-(--studio-glass-border) px-4 py-3 sm:px-6">
            <Dialog.Title className="line-clamp-2 min-w-0 text-sm font-semibold text-foreground [overflow-wrap:anywhere]">
              {shown?.title}
            </Dialog.Title>
            <div className="flex shrink-0 items-center gap-1">
              {shown && (
                <Link href={studioPaperPath(shown.id)} className={cn(GHOST_BUTTON, "h-9 px-2.5")}>
                  {t("openPage")}
                  <ArrowUpRightIcon aria-hidden />
                </Link>
              )}
              <Dialog.Close aria-label={tCommon("close")} className={ICON_BUTTON}>
                <XIcon aria-hidden />
              </Dialog.Close>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6">
            {shown && <PaperDetailContent paperId={shown.id} variant="sheet" />}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
