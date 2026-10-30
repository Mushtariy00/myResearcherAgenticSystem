import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { safeNextPath } from "@/lib/safe-redirect";
import { getSession } from "@/lib/session";
import { StudioLoginForm } from "@/studio/components/auth/studio-login-form";
import { STUDIO_DASHBOARD_PATH } from "@/studio/lib/login-redirect";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.login");
  return { title: t("title") };
}

/** After signing in, the visitor goes to `next` (checked by safeNextPath) or the dashboard. */
export default async function StudioLoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { next } = await searchParams;
  const target = safeNextPath(typeof next === "string" ? next : undefined, STUDIO_DASHBOARD_PATH);
  if (await getSession()) {
    redirect(target);
  }
  return <StudioLoginForm next={target} />;
}
