import { ArrowLeftIcon, CheckIcon } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";
import type { ReactNode } from "react";
import { LocaleSwitcher } from "@/components/app/locale-switcher";
import { ThemeToggle } from "@/components/app/theme-toggle";
import { STUDIO_PREFIX } from "@/lib/ui-version";
import { cn } from "@/lib/utils";
import { AuroraBackground } from "@/studio/components/effects/aurora-background";
import { GradientText } from "@/studio/components/effects/gradient-text";
import { PipelineGraph } from "@/studio/components/pipeline-graph";
import { StudioBrand } from "@/studio/components/studio-brand";
import { GHOST_BUTTON, SHARED_CONTROL } from "@/studio/lib/ui";

const PANEL_NODES = [
  { stage: "literature", status: "approved" },
  { stage: "method", status: "approved" },
  { stage: "coding", status: "running" },
  { stage: "experiment", status: "pending" },
  { stage: "writing", status: "pending" },
] as const;

/**
 * Studio sign-in pages: a split screen with the aurora and the product story on one side and a
 * glass form on the other. On phones the aurora shrinks to a band above the form.
 */
export default async function StudioAuthLayout({ children }: { children: ReactNode }) {
  const t = await getTranslations();
  const points = [
    t("studio.auth.points.approve"),
    t("studio.auth.points.budget"),
    t("studio.auth.points.languages"),
  ];

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section
        aria-labelledby="studio-auth-panel-title"
        className="relative isolate flex overflow-hidden border-b border-(--studio-glass-border) lg:sticky lg:top-0 lg:h-dvh lg:border-r lg:border-b-0"
      >
        <AuroraBackground variant="vivid" />
        <div className="flex w-full flex-col justify-between gap-4 px-5 py-5 sm:gap-8 sm:px-10 sm:py-10 lg:px-14 lg:py-12">
          <StudioBrand href={STUDIO_PREFIX} className="w-fit" />
          <p className="text-sm text-pretty text-muted-foreground sm:hidden">
            {t("studio.auth.panelBody")}
          </p>
          <div className="hidden max-w-xl gap-6 sm:grid">
            <p className="text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">
              {t("studio.auth.panelEyebrow")}
            </p>
            <h2
              id="studio-auth-panel-title"
              className="studio-display text-4xl text-foreground xl:text-5xl"
            >
              <GradientText>{t("studio.auth.panelTitle")}</GradientText>
            </h2>
            <p className="max-w-md text-base text-pretty text-muted-foreground">
              {t("studio.auth.panelBody")}
            </p>
            <ul className="grid gap-3">
              {points.map((point) => (
                <li key={point} className="flex items-start gap-3 text-sm text-foreground">
                  <span
                    aria-hidden
                    data-tone="success"
                    className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-(--tone)/15 text-(--tone-fg)"
                  >
                    <CheckIcon className="size-3.5" />
                  </span>
                  {point}
                </li>
              ))}
            </ul>
          </div>
          <div aria-hidden className="hidden lg:block">
            <PipelineGraph nodes={PANEL_NODES} size="compact" />
          </div>
        </div>
      </section>
      <div className="relative flex min-w-0 flex-col">
        <header className="flex items-center justify-between gap-2 px-4 py-3 sm:px-8 sm:py-5">
          <Link href={STUDIO_PREFIX} className={cn(GHOST_BUTTON, "-ml-2")}>
            <ArrowLeftIcon aria-hidden />
            {t("studio.auth.backHome")}
          </Link>
          <div className="flex items-center gap-1">
            <div className={SHARED_CONTROL}>
              <LocaleSwitcher />
            </div>
            <div className={SHARED_CONTROL}>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main
          id="studio-main"
          className="flex flex-1 items-start justify-center px-4 pt-4 pb-16 sm:items-center sm:px-8 sm:pt-0"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
