"use client";

import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { STUDIO_ROUTES } from "@/studio/lib/nav";
import { GHOST_BUTTON } from "@/studio/lib/ui";
import { PaperDetailContent } from "./paper-detail-content";

/** `/studio/papers/[...paperId]`: one library paper, with a way back to the library. */
export function StudioPaperDetail({ paperId }: { paperId: string }) {
  const t = useTranslations("studioWork.papers.detail");
  return (
    <div className="grid min-w-0 gap-6">
      <Link href={STUDIO_ROUTES.papers} className={cn(GHOST_BUTTON, "-ml-3 h-8 w-fit px-3")}>
        <ArrowLeftIcon aria-hidden />
        {t("backToLibrary")}
      </Link>
      <PaperDetailContent paperId={paperId} variant="page" />
    </div>
  );
}
