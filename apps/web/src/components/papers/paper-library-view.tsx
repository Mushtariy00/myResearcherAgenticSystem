"use client";

import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/app/query-state";
import { PaperBrowser } from "./paper-browser";

/** /papers: every paper the runs of the caller's projects have found. */
export function PaperLibraryView() {
  const t = useTranslations("papers");
  return (
    <>
      <PageHeader title={t("title")} description={t("description")} />
      <PaperBrowser />
    </>
  );
}
