"use client";

import { useQuery } from "@tanstack/react-query";
import { client } from "@/client/client.gen";

/** The part of `NotificationList` (GET /api/v1/me/notifications) Studio needs today. */
type NotificationListResponse = { 200: { unread_count?: unknown } };

export const unreadNotificationsQueryKey = ["studio", "me", "notifications", "unread"] as const;

const REFRESH_MS = 60_000;

async function fetchUnreadCount(signal: AbortSignal): Promise<number> {
  const { data } = await client.get<NotificationListResponse, unknown, true>({
    url: "/api/v1/me/notifications",
    signal,
    throwOnError: true,
  });
  const count = data?.unread_count;
  if (typeof count !== "number" || !Number.isFinite(count) || count < 0) {
    throw new Error("Unexpected notifications response");
  }
  return Math.floor(count);
}

export type UnreadNotifications = {
  /** The unread count; null while loading or when unavailable. */
  count: number | null;
  /** The endpoint failed (or does not exist yet): hide badges and tiles rather than guess. */
  unavailable: boolean;
};

/**
 * The signed-in user's unread notification count. Refreshes every minute and on window focus,
 * and stops polling after an error (for instance while the API has no notifications endpoint).
 *
 * The generated client has no `listNotificationsOptions` yet (regenerate it from the API's
 * OpenAPI and switch to it); until then this calls the endpoint through the generated client's
 * untyped `get`, which still turns failures into ApiError (src/lib/api-client.ts).
 */
export function useUnreadNotifications(): UnreadNotifications {
  const query = useQuery({
    queryKey: unreadNotificationsQueryKey,
    queryFn: ({ signal }) => fetchUnreadCount(signal),
    retry: false,
    refetchInterval: (current) => (current.state.status === "error" ? false : REFRESH_MS),
    refetchOnWindowFocus: true,
  });
  return { count: query.isSuccess ? query.data : null, unavailable: query.isError };
}
