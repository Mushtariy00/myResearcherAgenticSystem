/**
 * Test-only: renders the Classic project, paper and dashboard pages with what they expect around
 * them (React Query, next-intl with the real messages, the signed-in user), plus the browser
 * APIs jsdom lacks. Requests go to a fetch mock (`mockApi` in src/hooks/run-hooks.fixtures.tsx).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement, ReactNode } from "react";
import { vi } from "vitest";
import { CurrentUserProvider } from "@/components/app/current-user";
import type { Locale } from "@/i18n/config";
import type { SessionUser } from "@/lib/session-user";
import { enMessages, koMessages } from "@/test/messages";

export const OWNER: SessionUser = {
  id: "user-owner",
  name: "Ada Lovelace",
  email: "ada@lab.example",
  role: "user",
};

export const RESEARCHER: SessionUser = {
  id: "user-researcher",
  name: "Grace Hopper",
  email: "grace@lab.example",
  role: "user",
};

export const LAB_ADMIN: SessionUser = {
  id: "user-admin",
  name: "Katherine Johnson",
  email: "katherine@lab.example",
  role: "admin",
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

export function renderPage(
  ui: ReactElement,
  {
    user = OWNER,
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
        <CurrentUserProvider user={user}>{children}</CurrentUserProvider>
      </NextIntlClientProvider>
    </QueryClientProvider>
  );
  const view = render(wrap(ui));
  return { ...view, queryClient, rerender: (next: ReactElement) => view.rerender(wrap(next)) };
}

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function matchMedia(query: string): MediaQueryList {
  return {
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  } as unknown as MediaQueryList;
}

/**
 * Opens a Base UI select and picks an option, as a mouse would: the option only takes a click
 * that started on it (a pointer press), so it is pressed first.
 */
export async function chooseOption(trigger: HTMLElement, option: string): Promise<void> {
  fireEvent.click(trigger);
  const item = await screen.findByRole("option", { name: option });
  fireEvent.pointerDown(item);
  fireEvent.click(item);
}

/** Browser APIs Base UI and the pages use that jsdom does not have (call in beforeAll). */
export function installBrowserStubs(): void {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  Object.defineProperty(window, "matchMedia", { configurable: true, value: matchMedia });
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
}
