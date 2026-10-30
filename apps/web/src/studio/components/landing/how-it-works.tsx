import { BotIcon, FileCheckIcon, MessageSquareTextIcon, PlayIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";
import { glassClassName } from "@/studio/lib/glass";
import { SectionHeading } from "./section-heading";

const STEPS = [
  { key: "ask", icon: PlayIcon, stage: "literature" },
  { key: "agents", icon: BotIcon, stage: "method" },
  { key: "review", icon: MessageSquareTextIcon, stage: "coding" },
  { key: "paper", icon: FileCheckIcon, stage: "writing" },
] as const;

/**
 * The four steps of a run as glass cards. On desktops a short beam in the stage colours joins
 * each card to the next across the gap between them, level with the icons, so it never shows
 * through the translucent cards or crosses their numbers.
 */
export function LandingHowItWorks() {
  const t = useTranslations("studio.landing.how");
  return (
    <section
      id="how"
      aria-labelledby="studio-how-title"
      className="scroll-mt-20 px-4 py-20 sm:px-6 lg:py-28"
    >
      <div className="mx-auto grid w-full max-w-6xl gap-12">
        <SectionHeading
          id="studio-how-title"
          eyebrow={t("eyebrow")}
          title={t("title")}
          tone="warning"
        />
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 lg:gap-6">
          {STEPS.map(({ key, icon: Icon, stage }, index) => {
            const next = STEPS[index + 1];
            return (
              <li
                key={key}
                data-stage={stage}
                className={cn(glassClassName(), "flex flex-col gap-4 p-6")}
              >
                <div className="relative flex items-center justify-between">
                  <span
                    aria-hidden
                    className="flex size-10 items-center justify-center rounded-xl border border-(--tone)/30 bg-(--studio-surface) text-(--tone-fg)"
                  >
                    <Icon className="size-5" />
                  </span>
                  <span
                    aria-hidden
                    className="font-mono text-xs text-muted-foreground tabular-nums"
                  >
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {/* Starts at the card's outer edge (past p-6 and the 1px border) and spans
                      the lg:gap-6 gap exactly. */}
                  {next && (
                    <span
                      aria-hidden
                      data-connector=""
                      className="pointer-events-none absolute top-1/2 left-[calc(100%+1.5rem+1px)] hidden h-0.5 w-6 -translate-y-1/2 rounded-full bg-linear-to-r from-(--tone)/70 to-(--next-tone)/70 lg:block"
                      style={{ "--next-tone": `var(--stage-${next.stage})` } as CSSProperties}
                    />
                  )}
                </div>
                <div className="grid gap-1.5">
                  <h3 className="text-base font-semibold tracking-tight text-foreground">
                    {t(`steps.${key}.title`)}
                  </h3>
                  <p className="text-sm leading-relaxed text-pretty text-muted-foreground">
                    {t(`steps.${key}.body`)}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
