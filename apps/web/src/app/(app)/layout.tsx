import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";
import { AppHeader } from "@/components/app/app-header";
import { CurrentUserProvider } from "@/components/app/current-user";
import { getSession } from "@/lib/session";
import { toSessionUser } from "@/lib/session-user";

/** Every page in this group needs a valid Better Auth session (the proxy only checks a cookie). */
export default async function AppLayout({ children }: { children: ReactNode }) {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }
  const t = await getTranslations("nav");
  return (
    <CurrentUserProvider user={toSessionUser(session.user)}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:ring-3 focus:ring-ring/50"
      >
        {t("skipToContent")}
      </a>
      <div className="flex min-h-dvh flex-col">
        <AppHeader />
        <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8">
          {children}
        </main>
      </div>
    </CurrentUserProvider>
  );
}
