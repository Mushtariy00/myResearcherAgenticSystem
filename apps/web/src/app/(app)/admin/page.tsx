import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { AdminView } from "@/components/admin/admin-view";
import { getSession } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("admin");
  return { title: t("title") };
}

export default async function AdminPage() {
  const session = await getSession();
  // Lab admins only; Better Auth and FastAPI enforce the same rule on every call.
  if (session?.user.role !== "admin") {
    notFound();
  }
  return <AdminView />;
}
