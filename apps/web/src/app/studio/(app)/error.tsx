"use client";

import { RotateCwIcon, TriangleAlertIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";

/** Unexpected rendering errors inside the Studio shell (API failures are shown inline instead). */
export default function StudioAppError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("errorPage");
  return (
    <StudioStatePanel
      icon={<TriangleAlertIcon aria-hidden />}
      tone="danger"
      title={t("title")}
      description={t("description")}
    >
      <button type="button" onClick={reset} className={OUTLINE_BUTTON}>
        <RotateCwIcon aria-hidden />
        {t("retry")}
      </button>
    </StudioStatePanel>
  );
}
