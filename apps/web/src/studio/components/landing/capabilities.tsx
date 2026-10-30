import {
  CircleCheckIcon,
  CircleXIcon,
  ContainerIcon,
  GaugeIcon,
  LanguagesIcon,
  RotateCcwIcon,
  UserCheckIcon,
  WorkflowIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { STAGE_ORDER } from "@/lib/timeline";
import { BentoCard, BentoGrid } from "@/studio/components/effects/bento-grid";
import { STAGE_ICONS } from "@/studio/lib/stages";
import { SectionHeading } from "./section-heading";

const CHIP =
  "inline-flex h-7 items-center gap-1.5 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2.5 text-xs font-medium text-(--tone-fg)";

/**
 * What the platform does, stated plainly (no customers, quotes or usage numbers). The spans fill
 * every row, which a test checks: on tablets the stages card takes a row and the other four pair
 * up; on desktops the six tracks hold 4 + 2, then 2 + 2 + 2.
 */
export function LandingCapabilities() {
  const t = useTranslations();
  return (
    <section
      id="capabilities"
      aria-labelledby="studio-capabilities-title"
      className="scroll-mt-20 px-4 py-20 sm:px-6 lg:py-28"
    >
      <div className="mx-auto grid w-full max-w-6xl gap-12">
        <SectionHeading
          id="studio-capabilities-title"
          eyebrow={t("studio.landing.capabilities.eyebrow")}
          title={t("studio.landing.capabilities.title")}
          subtitle={t("studio.landing.capabilities.subtitle")}
        />
        <BentoGrid>
          <BentoCard
            className="sm:col-span-2 lg:col-span-4"
            icon={WorkflowIcon}
            tone="info"
            title={t("studio.landing.capabilities.stages.title")}
            description={t("studio.landing.capabilities.stages.body")}
            spotlightColor="var(--aurora-cyan)"
          >
            <ol className="flex flex-wrap gap-2">
              {STAGE_ORDER.map((stage, index) => {
                const Icon = STAGE_ICONS[stage];
                return (
                  <li key={stage} data-stage={stage} className={CHIP}>
                    <span aria-hidden className="font-mono text-[0.65rem] opacity-80">
                      {index + 1}
                    </span>
                    <Icon aria-hidden className="size-3.5" />
                    {t(`stages.${stage}`)}
                  </li>
                );
              })}
            </ol>
          </BentoCard>
          <BentoCard
            className="lg:col-span-2"
            icon={UserCheckIcon}
            tone="success"
            title={t("studio.landing.capabilities.approval.title")}
            description={t("studio.landing.capabilities.approval.body")}
            spotlightColor="var(--aurora-emerald)"
          >
            <ul className="flex flex-wrap gap-2">
              <li data-tone="success" className={CHIP}>
                <CircleCheckIcon aria-hidden className="size-3.5" />
                {t("run.approval.approve")}
              </li>
              <li data-tone="warning" className={CHIP}>
                <RotateCcwIcon aria-hidden className="size-3.5" />
                {t("run.approval.requestChanges")}
              </li>
              <li data-tone="danger" className={CHIP}>
                <CircleXIcon aria-hidden className="size-3.5" />
                {t("run.approval.reject")}
              </li>
            </ul>
          </BentoCard>
          <BentoCard
            className="lg:col-span-2"
            icon={GaugeIcon}
            tone="warning"
            title={t("studio.landing.capabilities.budget.title")}
            description={t("studio.landing.capabilities.budget.body")}
            spotlightColor="var(--aurora-violet)"
          >
            <div aria-hidden className="grid gap-2">
              <div className="flex h-2 overflow-hidden rounded-full bg-(--studio-glass-strong)">
                <span data-stage="method" className="h-full w-[62%] bg-(--tone)" />
                <span data-stage="experiment" className="h-full w-[38%] bg-(--tone)/60" />
              </div>
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{t("studio.landing.capabilities.budget.paid")}</span>
                <span>{t("studio.landing.capabilities.budget.free")}</span>
              </div>
            </div>
          </BentoCard>
          <BentoCard
            className="lg:col-span-2"
            icon={ContainerIcon}
            stage="experiment"
            title={t("studio.landing.capabilities.sandbox.title")}
            description={t("studio.landing.capabilities.sandbox.body")}
            spotlightColor="var(--aurora-emerald)"
          >
            <ul className="flex flex-wrap gap-1.5">
              {(["image", "code", "config", "dataset", "seed"] as const).map((item) => (
                <li
                  key={item}
                  className="rounded-md border border-(--studio-glass-border) bg-(--studio-glass) px-2 py-1 font-mono text-[0.7rem] text-muted-foreground"
                >
                  {t(`studio.landing.capabilities.sandbox.provenance.${item}`)}
                </li>
              ))}
            </ul>
          </BentoCard>
          <BentoCard
            className="lg:col-span-2"
            icon={LanguagesIcon}
            stage="writing"
            title={t("studio.landing.capabilities.languages.title")}
            description={t("studio.landing.capabilities.languages.body")}
            spotlightColor="var(--aurora-indigo)"
          >
            <ul className="flex flex-wrap gap-2">
              <li lang="en" data-tone="info" className={CHIP}>
                {t("nav.languages.en")}
              </li>
              <li lang="ko" data-tone="info" className={CHIP}>
                {t("nav.languages.ko")}
              </li>
            </ul>
          </BentoCard>
        </BentoGrid>
      </div>
    </section>
  );
}
