import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { NotificationsView } from "@/components/notifications/notifications-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("notifications");
  return { title: t("title") };
}

export default function NotificationsPage() {
  return <NotificationsView />;
}
