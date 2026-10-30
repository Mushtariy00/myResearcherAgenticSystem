"use client";

import { Dialog } from "@base-ui/react/dialog";
import { XIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect } from "react";
import { cn } from "@/lib/utils";
import { StudioBrand } from "@/studio/components/studio-brand";
import { useMediaQuery } from "@/studio/hooks/use-media-query";
import { STUDIO_ROUTES } from "@/studio/lib/nav";
import { ICON_BUTTON } from "@/studio/lib/ui";
import { StudioNavList } from "./studio-nav-list";
import { StudioUserCard } from "./user-card";

/**
 * Below lg the sidebar becomes a sheet that slides in from the start edge (a modal dialog:
 * focus is trapped, Escape and the backdrop close it). Following a link closes it, and so does
 * widening the window to the desktop layout.
 */
export function StudioMobileNav({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("studio.shell");
  const desktop = useMediaQuery("(min-width: 64rem)");

  useEffect(() => {
    if (desktop && open) {
      onOpenChange(false);
    }
  }, [desktop, open, onOpenChange]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-[oklch(0.1_0.02_265/0.5)] transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none" />
        <Dialog.Popup
          className={cn(
            "studio-glass studio-blur fixed inset-y-0 left-0 z-50 flex w-[min(20rem,calc(100vw-3rem))] flex-col rounded-none rounded-r-2xl border-y-0 border-l-0 bg-(--studio-glass-strong) px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] outline-none",
            "transition-[translate] duration-300 ease-out data-ending-style:-translate-x-full data-starting-style:-translate-x-full motion-reduce:transition-none",
          )}
        >
          <Dialog.Title className="sr-only">{t("navigation")}</Dialog.Title>
          <div className="flex h-11 items-center justify-between gap-2 px-1.5">
            <StudioBrand href={STUDIO_ROUTES.dashboard} />
            <Dialog.Close aria-label={t("closeMenu")} className={cn(ICON_BUTTON, "-mr-1.5")}>
              <XIcon aria-hidden />
            </Dialog.Close>
          </div>
          {/* Reaches 4px past the items: the scroll box clips, and focus rings must stay whole. */}
          <div className="-mx-1 mt-4 min-h-0 flex-1 overflow-y-auto p-1">
            <StudioNavList layoutGroup="studio-nav-sheet" onNavigate={() => onOpenChange(false)} />
          </div>
          <div className="border-t border-(--studio-glass-border) pt-3">
            <StudioUserCard />
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
