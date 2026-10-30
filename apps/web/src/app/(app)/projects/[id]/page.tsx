import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { ProjectView } from "@/components/projects/project-view";
import { isUuid } from "@/lib/ids";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("project");
  return { title: t("title") };
}

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) {
    notFound();
  }
  // Keyed so another project opens on its own tab and filters.
  return <ProjectView key={id} projectId={id} />;
}
