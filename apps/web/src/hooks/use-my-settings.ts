"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getMySettingsOptions, updateMySettingsMutation } from "@/client/@tanstack/react-query.gen";

/**
 * Saves some of the signed-in user's settings: PUT /api/v1/me/settings with only those fields,
 * so a language switch never undoes an email choice made in another tab. Shown at once where
 * the settings are loaded and put back if the API refuses; saves run one after another, so the
 * last change wins.
 */
export function useUpdateMySettings() {
  const queryClient = useQueryClient();
  const { queryKey } = getMySettingsOptions(); // typed with the settings
  const mutationKey = ["updateMySettings"];
  const isOnlySave = () => queryClient.isMutating({ mutationKey }) === 1;
  return useMutation({
    ...updateMySettingsMutation(),
    mutationKey,
    scope: { id: "my-settings" },
    onMutate: async ({ body }) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData(queryKey);
      if (previous) {
        queryClient.setQueryData(queryKey, {
          email_notifications: body.email_notifications ?? previous.email_notifications,
          locale: body.locale ?? previous.locale,
        });
      }
      return { previous };
    },
    onError: (_error, _variables, context) => {
      // With other saves queued, they carry this change on; their outcome decides.
      if (isOnlySave() && context?.previous) {
        queryClient.setQueryData(queryKey, context.previous);
      }
    },
    onSuccess: (saved) => {
      if (isOnlySave()) {
        queryClient.setQueryData(queryKey, saved);
      }
    },
  });
}

/** The signed-in user's settings and the switch for notification emails (both profile pages). */
export function useMySettings() {
  const query = useQuery(getMySettingsOptions());
  const update = useUpdateMySettings();
  return {
    query,
    setEmailNotifications: (enabled: boolean) =>
      update.mutate({ body: { email_notifications: enabled } }),
    saving: update.isPending,
    /** Why the last change was not saved; cleared when the next one starts. */
    saveError: update.error,
  };
}
