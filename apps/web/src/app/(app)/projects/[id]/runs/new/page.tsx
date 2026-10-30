import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { NewRunView } from "@/components/projects/new-run/new-run-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("wizard");
  return { title: t("title") };
}

export default async function NewRunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  // Keyed: the wizard's form belongs to one project.
  return <NewRunView key={id} projectId={id} />;
}
