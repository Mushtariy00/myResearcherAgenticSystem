import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { parseAdminTab } from "@/components/admin/admin-sections";
import { AdminView } from "@/components/admin/admin-view";
import { getSession } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin");
  return { title: t("title") };
}

/** `?tab=` opens one section (users, budgets, routing, balance, health, audit). */
export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const session = await getSession();
  // Lab admins only; Better Auth and FastAPI enforce the same rule on every call.
  if (session?.user.role !== "admin") {
    notFound();
  }
  const { tab } = await searchParams;
  return <AdminView initialTab={parseAdminTab(tab)} />;
}
