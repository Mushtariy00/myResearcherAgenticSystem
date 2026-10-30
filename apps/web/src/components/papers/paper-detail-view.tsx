"use client";

import { ChevronLeftIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { LoadingRows, PageHeader, QueryError } from "@/components/app/query-state";
import { DemoBadge } from "@/components/shared/demo-badge";
import { usePaper } from "@/hooks/use-paper";
import { PaperByline, PaperDetailBody } from "./paper-detail-body";
import { PAPER_LIBRARY_PATH } from "./paper-href";

/** /papers/<id>: one paper with the analyses of every run that read it, and its PDF. */
export function PaperDetailView({ paperId }: { paperId: string }) {
  const t = useTranslations("papers.detail");
  const paper = usePaper(paperId);

  const back = (
    <Link
      href={PAPER_LIBRARY_PATH}
      className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ChevronLeftIcon className="size-4" aria-hidden />
      {t("back")}
    </Link>
  );

  if (paper.isPending) {
    return (
      <>
        {back}
        <LoadingRows rows={5} />
      </>
    );
  }
  if (paper.isError) {
    return (
      <>
        {back}
        <QueryError error={paper.error} onRetry={() => paper.refetch()} />
      </>
    );
  }

  return (
    <>
      {back}
      <PageHeader
        title={paper.data.paper.title}
        description={<PaperByline paper={paper.data.paper} />}
      >
        {paper.data.demo && (
          <div className="pt-1">
            <DemoBadge demo />
          </div>
        )}
      </PageHeader>
      <PaperDetailBody detail={paper.data} layout="page" />
    </>
  );
}
