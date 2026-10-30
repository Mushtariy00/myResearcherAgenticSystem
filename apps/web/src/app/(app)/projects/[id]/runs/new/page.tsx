import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { NewRunView } from "@/components/projects/new-run/new-run-view";
import { isUuid } from "@/lib/ids";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("wizard");
  return { title: t("title") };
}

export default async function NewRunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) {
    notFound();
  }
  // Keyed: the wizard's form belongs to one project.
  return <NewRunView key={id} projectId={id} />;
}
