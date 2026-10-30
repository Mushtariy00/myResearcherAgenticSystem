import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StudioProfileView } from "@/studio/components/profile/studio-profile-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("profile");
  return { title: t("title") };
}

export default function StudioProfilePage() {
  return <StudioProfileView />;
}
