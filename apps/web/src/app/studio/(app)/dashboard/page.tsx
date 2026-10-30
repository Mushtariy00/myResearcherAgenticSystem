import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StudioDashboard } from "@/studio/components/dashboard/studio-dashboard";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("dashboard");
  return { title: t("title") };
}

export default function StudioDashboardPage() {
  return <StudioDashboard />;
}
