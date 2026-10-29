"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { SquareIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";
import { cancelRunMutation, getRunQueryKey } from "@/client/@tanstack/react-query.gen";
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
import { useErrorMessage } from "@/hooks/use-error-message";
import { toApiError } from "@/lib/api-error";

export function CancelRunButton({ runId }: { runId: string }) {
  const t = useTranslations("run.cancel");
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const cancel = useMutation({
    ...cancelRunMutation(),
    onSuccess: () => toast.success(t("requested")),
    onError: (error) => {
      if (toApiError(error).code === "run.already_finished") {
        toast.info(errorMessage(error));
      } else {
        toast.error(errorMessage(error));
      }
    },
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: getRunQueryKey({ path: { run_id: runId } }) }),
  });

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger
        render={
          <Button variant="outline" disabled={cancel.isPending}>
            <SquareIcon aria-hidden />
            {cancel.isPending ? t("cancelling") : t("button")}
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
              cancel.mutate({ path: { run_id: runId } });
            }}
          >
            {t("confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
