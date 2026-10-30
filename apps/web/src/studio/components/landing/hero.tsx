import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";
import { GradientText } from "@/studio/components/effects/gradient-text";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { TiltCard } from "@/studio/components/effects/tilt-card";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";
import type { LandingCta } from "./landing-cta";
import { PipelineDemo } from "./pipeline-demo";

const rise = (ms: number) => ({ "--rise-delay": `${ms}ms` }) as CSSProperties;

export function LandingHero({ cta, signedIn }: { cta: LandingCta; signedIn: boolean }) {
  const t = useTranslations("studio.landing.hero");
  return (
    <section
      aria-labelledby="studio-hero-title"
      className="relative px-4 pt-14 pb-20 sm:px-6 sm:pt-20 lg:pt-28"
    >
      <div className="mx-auto grid w-full max-w-6xl gap-14 lg:gap-20">
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <p className="studio-rise studio-glass inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-foreground">
            <PulseDot tone="success" live />
            {t("eyebrow")}
          </p>
          <h1
            id="studio-hero-title"
            className="studio-rise studio-display mt-7 text-[2.6rem] text-foreground sm:text-6xl lg:text-7xl"
            style={rise(80)}
          >
            <span className="block">{t("titleLead")}</span>
            <GradientText className="block pb-1">{t("titleAccent")}</GradientText>
          </h1>
          <p
            className="studio-rise mt-6 max-w-2xl text-base text-pretty text-muted-foreground sm:text-lg"
            style={rise(160)}
          >
            {t("subtitle")}
          </p>
          <div
            className="studio-rise mt-9 flex w-full flex-col items-stretch justify-center gap-3 sm:w-auto sm:flex-row sm:items-center"
            style={rise(240)}
          >
            <ShimmerButton size="lg" render={<Link href={cta.href} />}>
              {cta.label}
              <ArrowRightIcon aria-hidden />
            </ShimmerButton>
            <a href="#how" className={cn(OUTLINE_BUTTON, "h-12 px-6 text-base")}>
              {t("secondary")}
            </a>
          </div>
          {!signedIn && (
            <p className="studio-rise mt-4 text-xs text-muted-foreground" style={rise(300)}>
              {t("inviteOnly")}
            </p>
          )}
        </div>
        <div className="studio-rise mx-auto w-full max-w-5xl" style={rise(360)}>
          <TiltCard maxTilt={2.5}>
            <PipelineDemo />
          </TiltCard>
        </div>
      </div>
    </section>
  );
}
