import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { RunView } from "@/components/runs/run-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("run");
  return { title: t("title") };
}

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Keyed so moving to another run starts with a fresh event stream and log.
  return <RunView key={id} runId={id} />;
}
