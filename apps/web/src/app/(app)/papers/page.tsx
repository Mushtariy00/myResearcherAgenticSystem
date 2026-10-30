import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { PaperLibraryView } from "@/components/papers/paper-library-view";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("papers");
  return { title: t("title") };
}

export default function PapersPage() {
  return <PaperLibraryView />;
}
