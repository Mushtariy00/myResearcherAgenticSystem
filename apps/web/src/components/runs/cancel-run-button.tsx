"use client";

import { SquareIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useCancelRun } from "@/hooks/use-cancel-run";
import { useErrorMessage } from "@/hooks/use-error-message";

/** Cancels the run after a confirmation (useCancelRun); a run that already ended is no error. */
export function CancelRunButton({ runId }: { runId: string }) {
  const t = useTranslations("run.cancel");
  const errorMessage = useErrorMessage();
  const [open, setOpen] = useState(false);
  const cancel = useCancelRun({
    onCancelled: () => toast.success(t("requested")),
    onAlreadyFinished: (_runId, error) => toast.info(errorMessage(error)),
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger
        render={
          <Button variant="outline" disabled={cancel.pending}>
            <SquareIcon aria-hidden />
            {cancel.pending ? t("cancelling") : t("button")}
          </Button>
        }
      />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("confirmTitle")}</AlertDialogTitle>
          <AlertDialogDescription>{t("confirmDescription")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("keepRunning")}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={() => {
              setOpen(false);
              cancel.cancel(runId);
            }}
          >
            {t("confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
