import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { ProjectView } from "@/components/projects/project-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("project");
  return { title: t("title") };
}

export default async function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectView projectId={id} />;
}
