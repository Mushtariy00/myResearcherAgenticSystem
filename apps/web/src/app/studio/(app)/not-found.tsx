import { CompassIcon } from "lucide-react";
import { getTranslations } from "next-intl/server";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { STUDIO_ROUTES } from "@/studio/lib/nav";

export default async function StudioNotFound() {
  const t = await getTranslations("studio.notFound");
  return (
    <StudioStatePanel
      icon={<CompassIcon aria-hidden />}
      code="404"
      title={t("title")}
      description={t("description")}
      action={{ href: STUDIO_ROUTES.dashboard, label: t("back") }}
    />
  );
}
