import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { LocaleSwitcher } from "@/components/app/locale-switcher";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { STUDIO_PREFIX } from "@/lib/ui-version";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { StudioMark } from "@/studio/components/studio-mark";
import { GHOST_BUTTON, SHARED_CONTROL } from "@/studio/lib/ui";
import type { LandingCta } from "./landing-cta";

const SECTIONS = ["capabilities", "how", "sources"] as const;

/**
 * The product name with the Studio mark. On a phone the language, theme and sign-in controls
 * leave too little room for the name on one line, so it wraps onto two (balanced) instead of
 * being cut off; from small tablets up it fits on one line.
 */
function LandingBrand() {
  const t = useTranslations();
  return (
    <Link
      href={STUDIO_PREFIX}
      className="flex min-w-0 items-center gap-2.5 rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <StudioMark />
      <span className="grid min-w-0 leading-tight">
        <span className="text-[0.8125rem] font-semibold tracking-tight text-balance [overflow-wrap:anywhere] text-foreground">
          {t("common.appName")}
        </span>
        <span className="text-[0.7rem] font-semibold tracking-[0.14em] text-(--studio-accent-fg) uppercase">
          {t("shell.version.studio")}
        </span>
      </span>
    </Link>
  );
}

export function LandingHeader({ cta }: { cta: LandingCta }) {
  const t = useTranslations("studio.landing.nav");
  return (
    <header className="studio-blur sticky top-0 z-30 border-b border-(--studio-glass-border) bg-(--studio-topbar)">
      <div className="mx-auto flex min-h-16 w-full max-w-6xl items-center gap-2 px-4 py-2 sm:px-6">
        <LandingBrand />
        <nav aria-label={t("label")} className="ml-6 hidden items-center gap-0.5 md:flex">
          {SECTIONS.map((section) => (
            <a key={section} href={`#${section}`} className={GHOST_BUTTON}>
              {t(section)}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex shrink-0 items-center gap-0.5 sm:gap-1">
          <div className={SHARED_CONTROL}>
            <LocaleSwitcher />
          </div>
          <div className={SHARED_CONTROL}>
            <ThemeToggle />
          </div>
          <ShimmerButton size="sm" className="ml-1" render={<Link href={cta.href} />}>
            {cta.label}
            <ArrowRightIcon aria-hidden className="hidden sm:block" />
          </ShimmerButton>
        </div>
      </div>
    </header>
  );
}
