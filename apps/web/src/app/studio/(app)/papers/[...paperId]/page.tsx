import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StudioPaperDetail } from "@/studio/components/papers/studio-paper-detail";
import { paperIdFromSegments } from "@/studio/lib/nav";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("studioWork.papers.detail");
  return { title: t("title") };
}

/**
 * `/studio/papers/<paper id>`: paper ids contain slashes and colons (`doi:10.5555/abc.12`), so
 * the route catches every segment; `paperIdFromSegments` decodes and joins them back into the
 * id (see `studioPaperPath`, which builds these URLs).
 */
export default async function StudioPaperPage({
  params,
}: {
  params: Promise<{ paperId: string[] }>;
}) {
  const { paperId } = await params;
  const id = paperIdFromSegments(paperId);
  return <StudioPaperDetail key={id} paperId={id} />;
}
