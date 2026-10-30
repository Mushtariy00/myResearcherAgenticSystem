import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { parseAdminTab } from "@/components/admin/admin-sections";
import { getSession } from "@/lib/session";
import { StudioAdminView } from "@/studio/components/admin/studio-admin-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin");
  return { title: t("title") };
}

/**
 * Lab admins only, as in Classic: anyone else gets the Studio not-found page (inside the
 * shell). `?tab=` opens one section.
 */
export default async function StudioAdminPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const session = await getSession();
  if (session?.user.role !== "admin") {
    notFound();
  }
  const { tab } = await searchParams;
  return <StudioAdminView initialTab={parseAdminTab(tab)} />;
}
