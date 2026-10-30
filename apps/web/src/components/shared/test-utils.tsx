/**
 * Test-only: renders shared components inside next-intl with the app's real messages, in the
 * chosen language (component tests opt into jsdom with `// @vitest-environment jsdom`).
 */
import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import type { Locale } from "@/i18n/config";
import { enMessages, koMessages } from "@/test/messages";

export function renderWithIntl(ui: ReactElement, { locale = "en" }: { locale?: Locale } = {}) {
  const wrap = (node: ReactElement) => (
    <NextIntlClientProvider
      locale={locale}
      messages={locale === "ko" ? koMessages : enMessages}
      timeZone="Asia/Seoul"
    >
      {node}
    </NextIntlClientProvider>
  );
  const view = render(wrap(ui));
  return { ...view, rerender: (next: ReactElement) => view.rerender(wrap(next)) };
}
