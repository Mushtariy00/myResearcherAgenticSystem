import { useTranslations } from "next-intl";
import { LandingCapabilities } from "./capabilities";
import { LandingHero } from "./hero";
import { LandingHowItWorks } from "./how-it-works";
import { landingCta } from "./landing-cta";
import { LandingClosing, LandingFooter } from "./landing-footer";
import { LandingHeader } from "./landing-header";
import { LandingSources } from "./sources";

/**
 * The public Studio landing page. `signedIn` (checked on the server) turns "Sign in" into
 * "Open dashboard". Every statement is a fact about the platform: no customers, testimonials or
 * usage numbers.
 */
export function LandingPage({ signedIn }: { signedIn: boolean }) {
  const t = useTranslations();
  const cta = landingCta(signedIn, {
    signIn: t("studio.landing.hero.signIn"),
    openDashboard: t("studio.landing.hero.openDashboard"),
  });

  return (
    <div className="relative flex min-h-dvh flex-col">
      <a
        href="#studio-main"
        className="sr-only rounded-[10px] bg-popover px-3 py-2 text-sm font-medium text-popover-foreground shadow-lg focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:outline-none focus:ring-3 focus:ring-ring/60"
      >
        {t("nav.skipToContent")}
      </a>
      <LandingHeader cta={cta} />
      <main id="studio-main" tabIndex={-1} className="flex-1 outline-none">
        <LandingHero cta={cta} signedIn={signedIn} />
        <LandingCapabilities />
        <LandingHowItWorks />
        <LandingSources />
        <LandingClosing cta={cta} />
      </main>
      <LandingFooter />
    </div>
  );
}
