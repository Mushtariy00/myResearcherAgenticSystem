"use client";

import { type UseQueryResult, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import type { NotificationList, NotificationOut } from "@/client";
import {
  listNotificationsOptions,
  markNotificationsReadMutation,
} from "@/client/@tanstack/react-query.gen";
import { type ApiError, toApiError } from "@/lib/api-error";
import { withNotificationsRead } from "@/lib/notifications";
import { POLL_INTERVALS, pollWhileVisible } from "@/lib/polling";
import type { ActionResult } from "./use-members";

/** The API takes at most this many keys per request. */
const MAX_KEYS = 500;

/** The list's cache key, typed with its data. */
function listKey() {
  return listNotificationsOptions().queryKey;
}

export type Notifications = {
  /** The list query (TanStack). Polls every 20 s while the page is visible, and on focus. */
  query: UseQueryResult<NotificationList, Error>;
  /** Newest first, at most 50 (see src/lib/notifications.ts to present them); [] until loaded. */
  items: NotificationOut[];
  /** Unread notifications overall (also beyond the 50 listed); null until loaded or when unavailable. */
  unreadCount: number | null;
  /** Marks these notifications read: at once on screen, put back if the API refuses. */
  markRead: (keys: readonly string[]) => Promise<ActionResult<NotificationList>>;
  /** Marks every current notification read, listed or not. */
  markAllRead: () => Promise<ActionResult<NotificationList>>;
  isMarking: boolean;
  /** Why the last mark failed (the list is back as it was); cleared when the next one starts. */
  markError: ApiError | null;
};

type Marking = readonly string[] | "all";

/**
 * The signed-in user's in-app notifications (approvals waiting or expiring, finished runs,
 * budget alerts) with the unread count, for the bell, the dashboard and the notifications page
 * of both interfaces.
 */
export function useNotifications(): Notifications {
  const queryClient = useQueryClient();
  const query = useQuery({
    ...listNotificationsOptions(),
    staleTime: 10_000,
    ...pollWhileVisible(POLL_INTERVALS.notifications),
  });

  const mutationKey = ["markNotificationsRead"];
  const isOnlyMark = () => queryClient.isMutating({ mutationKey }) === 1;
  const mark = useMutation({
    ...markNotificationsReadMutation(),
    mutationKey,
    onMutate: async (variables) => {
      const key = listKey();
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData(key);
      if (previous) {
        const marking: Marking = variables.body.all ? "all" : (variables.body.keys ?? []);
        queryClient.setQueryData(key, withNotificationsRead(previous, marking));
      }
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (isOnlyMark() && context?.previous) {
        queryClient.setQueryData(listKey(), context.previous);
      }
    },
    onSuccess: (list) => {
      // The answer is the whole list with read flags; a later mark's answer will include it.
      if (isOnlyMark()) {
        queryClient.setQueryData(listKey(), list);
      }
    },
    onSettled: (_list, error) => {
      if (error && isOnlyMark()) {
        void queryClient.invalidateQueries({ queryKey: listKey() });
      }
    },
  });
  const { mutateAsync } = mark;

  const send = useCallback(
    async (body: { keys: string[] } | { all: true }): Promise<ActionResult<NotificationList>> => {
      try {
        return { ok: true, data: await mutateAsync({ body }) };
      } catch (cause) {
        return { ok: false, error: toApiError(cause) };
      }
    },
    [mutateAsync],
  );

  const markRead = useCallback(
    (keys: readonly string[]) => {
      const list = queryClient.getQueryData(listKey());
      const read = new Set(list?.items.filter((item) => item.read).map((item) => item.key));
      // Only what is not read already; unknown keys go along (the API ignores them).
      const unread = [...new Set(keys)].filter((key) => key !== "" && !read.has(key));
      if (unread.length === 0) {
        // Nothing to send: the API would refuse an empty list.
        return Promise.resolve<ActionResult<NotificationList>>({
          ok: true,
          data: list ?? { items: [], unread_count: 0 },
        });
      }
      return send({ keys: unread.slice(0, MAX_KEYS) });
    },
    [queryClient, send],
  );

  const markAllRead = useCallback(() => send({ all: true }), [send]);

  return {
    query,
    items: query.data?.items ?? [],
    unreadCount: query.data?.unread_count ?? null,
    markRead,
    markAllRead,
    isMarking: mark.isPending,
    markError: mark.isError ? toApiError(mark.error) : null,
  };
}
