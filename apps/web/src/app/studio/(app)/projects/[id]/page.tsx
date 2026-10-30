import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StudioProjectView } from "@/studio/components/projects/studio-project-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("project");
  return { title: t("title") };
}

/** Next hands route params over URL-encoded. */
function decodeParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/** `/studio/projects/<id>?tab=runs|papers|members|settings`. */
export default async function StudioProjectPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const projectId = decodeParam(id);
  return (
    <StudioProjectView
      key={projectId}
      projectId={projectId}
      initialTab={typeof query.tab === "string" ? query.tab : undefined}
    />
  );
}
