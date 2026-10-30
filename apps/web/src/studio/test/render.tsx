/**
 * Test-only: renders Studio UI with the providers it expects (React Query, next-intl in the
 * chosen language, the Studio MotionConfig, and optionally a signed-in user).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MotionConfig } from "motion/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement, ReactNode } from "react";
import { CurrentUserProvider } from "@/components/app/current-user";
import type { Locale } from "@/i18n/config";
import type { SessionUser } from "@/lib/session-user";
import { enMessages, koMessages } from "@/test/messages";

export const TEST_USER: SessionUser = {
  id: "user-1",
  name: "Ada Lovelace",
  email: "ada@lab.example",
  role: "user",
};

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Number.POSITIVE_INFINITY } },
  });
}

export function renderStudio(
  ui: ReactElement,
  {
    locale = "en",
    user,
    queryClient = makeQueryClient(),
  }: { locale?: Locale; user?: SessionUser; queryClient?: QueryClient } = {},
) {
  const wrap = (children: ReactNode) => (
    <QueryClientProvider client={queryClient}>
      <NextIntlClientProvider
        locale={locale}
        messages={locale === "ko" ? koMessages : enMessages}
        timeZone="Asia/Seoul"
      >
        <MotionConfig reducedMotion="user">
          {user ? <CurrentUserProvider user={user}>{children}</CurrentUserProvider> : children}
        </MotionConfig>
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
  const view = render(wrap(ui));
  return { ...view, queryClient, rerender: (next: ReactElement) => view.rerender(wrap(next)) };
}
