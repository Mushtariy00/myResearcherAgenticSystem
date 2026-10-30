import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { StudioPapersLibrary } from "@/studio/components/papers/studio-papers-library";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("studioWork.papers");
  return { title: t("title") };
}

/** `/studio/papers?q=…`: the paper library, optionally opened on a search. */
export default async function StudioPapersPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { q } = await searchParams;
  return <StudioPapersLibrary initialQuery={typeof q === "string" ? q : ""} />;
}
