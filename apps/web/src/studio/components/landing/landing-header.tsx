import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { LocaleSwitcher } from "@/components/app/locale-switcher";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { STUDIO_PREFIX } from "@/lib/ui-version";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { StudioBrand } from "@/studio/components/studio-brand";
import { GHOST_BUTTON, SHARED_CONTROL } from "@/studio/lib/ui";
import type { LandingCta } from "./landing-cta";

const SECTIONS = ["capabilities", "how", "sources"] as const;

export function LandingHeader({ cta }: { cta: LandingCta }) {
  const t = useTranslations("studio.landing.nav");
  return (
    <header className="studio-blur sticky top-0 z-30 border-b border-(--studio-glass-border) bg-(--studio-topbar)">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-2 px-4 sm:px-6">
        <StudioBrand href={STUDIO_PREFIX} className="min-w-0 shrink" />
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
