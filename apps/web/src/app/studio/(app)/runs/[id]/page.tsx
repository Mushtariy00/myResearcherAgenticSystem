import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StudioRunPage } from "@/studio/components/runs/studio-run-page";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("run");
  return { title: t("title") };
}

export default async function StudioRunRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Keyed so moving to another run starts with a fresh event stream, log and review.
  return <StudioRunPage key={id} runId={id} />;
}
