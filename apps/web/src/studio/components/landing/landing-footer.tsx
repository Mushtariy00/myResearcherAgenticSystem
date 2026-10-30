import { ArrowRightIcon, LayoutTemplateIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { STUDIO_PREFIX } from "@/lib/ui-version";
import { cn } from "@/lib/utils";
import { GradientText } from "@/studio/components/effects/gradient-text";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { StudioBrand } from "@/studio/components/studio-brand";
import { glassClassName } from "@/studio/lib/glass";
import { GHOST_BUTTON } from "@/studio/lib/ui";
import type { LandingCta } from "./landing-cta";

export function LandingClosing({ cta }: { cta: LandingCta }) {
  const t = useTranslations("studio.landing.closing");
  return (
    <section aria-labelledby="studio-closing-title" className="px-4 pb-20 sm:px-6 lg:pb-28">
      <div
        className={cn(
          glassClassName(),
          "mx-auto flex w-full max-w-6xl flex-col items-start gap-6 overflow-hidden px-6 py-10 sm:px-10 sm:py-14 lg:flex-row lg:items-center lg:justify-between",
        )}
      >
        <div className="grid max-w-xl gap-3">
          <h2
            id="studio-closing-title"
            className="studio-display text-3xl text-foreground sm:text-4xl"
          >
            <GradientText>{t("title")}</GradientText>
          </h2>
          <p className="text-base text-pretty text-muted-foreground">{t("body")}</p>
        </div>
        <ShimmerButton size="lg" render={<Link href={cta.href} />}>
          {cta.label}
          <ArrowRightIcon aria-hidden />
        </ShimmerButton>
      </div>
    </section>
  );
}

export function LandingFooter() {
  const t = useTranslations("studio.landing.footer");
  return (
    <footer className="border-t border-(--studio-glass-border) px-4 py-10 sm:px-6">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="grid gap-2">
          <StudioBrand href={STUDIO_PREFIX} className="w-fit" />
          <p className="text-sm text-muted-foreground">{t("note")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>{t("classic")}</span>
          <Link href="/" prefetch={false} className={cn(GHOST_BUTTON, "text-foreground")}>
            <LayoutTemplateIcon aria-hidden />
            {t("openClassic")}
          </Link>
        </div>
      </div>
    </footer>
  );
}
