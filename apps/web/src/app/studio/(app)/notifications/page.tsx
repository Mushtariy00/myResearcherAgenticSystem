import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StudioNotificationsView } from "@/studio/components/notifications/studio-notifications-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("notifications");
  return { title: t("title") };
}

export default function StudioNotificationsPage() {
  return <StudioNotificationsView />;
}
