"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  getModelRoutingQueryKey,
  getPaidModelsOptions,
  getPaidModelsQueryKey,
  setPaidModelsMutation,
} from "@/client/@tanstack/react-query.gen";
import { useErrorMessage } from "@/hooks/use-error-message";

/**
 * The lab-wide kill switch for paid models (both interfaces): its state, and a toggle that
 * confirms with a toast. The model routing view shows the same state, so it is refreshed too.
 */
export function usePaidModels() {
  const t = useTranslations("admin.paidModels");
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const setting = useQuery(getPaidModelsOptions());
  const update = useMutation({
    ...setPaidModelsMutation(),
    onSuccess: async (data) => {
      queryClient.setQueryData(getPaidModelsQueryKey(), data);
      toast.success(data.enabled ? t("enabledToast") : t("disabledToast"));
      await queryClient.invalidateQueries({ queryKey: getModelRoutingQueryKey() });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return {
    setting,
    pending: update.isPending,
    setEnabled: (enabled: boolean) => update.mutate({ body: { enabled } }),
  };
}
