import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { PaperDetailView } from "@/components/papers/paper-detail-view";
import { paperIdFromSegments } from "@/components/papers/paper-href";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("papers.detail");
  return { title: t("title") };
}

/**
 * Paper ids contain slashes and colons (`doi:10.5555/depth.2024`): links encode the id as one
 * segment (paperHref), and a catch-all keeps it whole if a "/" arrives decoded.
 */
export default async function PaperPage({ params }: { params: Promise<{ paperId: string[] }> }) {
  const { paperId } = await params;
  const id = paperIdFromSegments(paperId);
  if (id === null) {
    notFound();
  }
  // Keyed so another paper starts with a fresh PDF position.
  return <PaperDetailView key={id} paperId={id} />;
}
