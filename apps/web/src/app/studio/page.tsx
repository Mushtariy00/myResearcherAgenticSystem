import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { getSession } from "@/lib/session";
import { LandingPage } from "@/studio/components/landing/landing-page";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("studio.meta");
  return { title: t("landingTitle"), description: t("landingDescription") };
}

/**
 * Studio's public landing page. The session only changes the call to action; if the session
 * check fails, the page still renders for a signed-out visitor.
 */
export default async function StudioLandingPage() {
  const session = await getSession().catch(() => null);
  return <LandingPage signedIn={Boolean(session)} />;
}
