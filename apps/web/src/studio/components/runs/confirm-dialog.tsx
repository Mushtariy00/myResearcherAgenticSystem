"use client";

import { AlertDialog } from "@base-ui/react/alert-dialog";
import { TriangleAlertIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";
import { DANGER_BUTTON } from "./run-ui";

export const STUDIO_BACKDROP =
  "fixed inset-0 z-50 bg-[oklch(0.1_0.02_265/0.5)] transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

/**
 * A glass confirmation for actions that cannot be undone (reject an output, cancel a run).
 * Focus starts on the safe choice, Escape keeps things as they are.
 */
export function StudioConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Portal>
        <AlertDialog.Backdrop className={STUDIO_BACKDROP} />
        <AlertDialog.Popup
          className={cn(
            "studio-glass fixed top-1/2 left-1/2 z-50 grid w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-2xl bg-popover p-5 text-popover-foreground outline-none sm:p-6",
            "transition-[scale,opacity] duration-200 ease-out data-ending-style:scale-[0.98] data-ending-style:opacity-0 data-starting-style:scale-[0.98] data-starting-style:opacity-0 motion-reduce:transition-none",
          )}
        >
          <div className="flex items-start gap-3">
            <span
              aria-hidden
              data-tone="danger"
              className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-(--tone)/30 bg-(--tone)/12 text-(--tone-fg)"
            >
              <TriangleAlertIcon className="size-4.5" />
            </span>
            <div className="grid min-w-0 gap-1.5">
              <AlertDialog.Title className="text-base font-semibold tracking-tight text-foreground">
                {title}
              </AlertDialog.Title>
              <AlertDialog.Description className="text-sm text-pretty text-muted-foreground">
                {description}
              </AlertDialog.Description>
            </div>
          </div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <AlertDialog.Close className={OUTLINE_BUTTON}>{cancelLabel}</AlertDialog.Close>
            <button type="button" className={DANGER_BUTTON} onClick={onConfirm}>
              {confirmLabel}
            </button>
          </div>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
