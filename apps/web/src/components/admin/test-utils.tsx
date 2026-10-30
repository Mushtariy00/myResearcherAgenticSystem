/**
 * Test-only: renders the admin, notifications and profile components of both interfaces with
 * what they expect around them (React Query, next-intl with the real messages, the Studio
 * MotionConfig, the signed-in user). API requests go to `mockApi` (src/hooks/run-hooks.fixtures).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MotionConfig } from "motion/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement, ReactNode } from "react";
import type { NotificationOut } from "@/client";
import { CurrentUserProvider } from "@/components/app/current-user";
import type { Locale } from "@/i18n/config";
import type { SessionUser } from "@/lib/session-user";
import { enMessages, koMessages } from "@/test/messages";

export const LAB_ADMIN: SessionUser = {
  id: "user-admin",
  name: "Katherine Johnson",
  email: "katherine@lab.example",
  role: "admin",
};

export const MEMBER: SessionUser = {
  id: "user-member",
  name: "Ada Lovelace",
  email: "ada@lab.example",
  role: "user",
};

/** No retries; data put in the cache stays fresh, so a test decides what is fetched. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Number.POSITIVE_INFINITY },
      mutations: { retry: false },
    },
  });
}

export function renderAs(
  ui: ReactElement,
  {
    user = MEMBER,
    queryClient = makeQueryClient(),
    locale = "en",
  }: { user?: SessionUser; queryClient?: QueryClient; locale?: Locale } = {},
) {
  const wrap = (children: ReactNode) => (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider
        locale={locale}
        messages={locale === "ko" ? koMessages : enMessages}
        timeZone="Asia/Seoul"
      >
        <MotionConfig reducedMotion="user">
          <CurrentUserProvider user={user}>{children}</CurrentUserProvider>
        </MotionConfig>
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
  const view = render(wrap(ui));
  return { ...view, queryClient, rerender: (next: ReactElement) => view.rerender(wrap(next)) };
}

export const RUN_ID = "22222222-2222-4222-8222-222222222222";
export const PROJECT_ID = "33333333-3333-4333-8333-333333333333";

/** A notification as GET /api/v1/me/notifications returns it. */
export function notification(overrides: Partial<NotificationOut> = {}): NotificationOut {
  return {
    key: `run.finished:${RUN_ID}`,
    kind: "run_completed",
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    read: false,
    run_id: RUN_ID,
    project_id: PROJECT_ID,
    stage: null,
    params: { topic: "Monocular depth", project: "Depth lab", error: null },
    ...overrides,
  };
}
