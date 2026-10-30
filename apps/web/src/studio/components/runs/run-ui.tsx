"use client";

import type { LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useId } from "react";
import type { TimelineStatus } from "@/lib/timeline";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { statusMeta, type Tone } from "@/studio/lib/stages";
import { OUTLINE_BUTTON } from "@/studio/lib/ui";

/* Buttons of the run page (10px radius, visible focus, disabled while a request is on its way). */

export const ACTION_BUTTON = cn(
  OUTLINE_BUTTON,
  "h-9 px-3 disabled:pointer-events-none disabled:opacity-60",
);

export const SMALL_BUTTON =
  "inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-2.5 text-xs font-medium text-foreground shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)] outline-none transition-colors hover:bg-(--studio-hover) focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-60 [&_svg]:size-3.5 [&_svg]:shrink-0";

/** A toggle (aria-pressed or aria-expanded) that takes the tone of its surroundings when on. */
export const TOGGLE_BUTTON = cn(
  SMALL_BUTTON,
  "aria-pressed:border-(--tone)/45 aria-pressed:bg-(--tone)/14 aria-expanded:border-(--tone)/45 aria-expanded:bg-(--tone)/14",
);

export const DANGER_BUTTON =
  "inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-[10px] border border-(--studio-danger)/40 bg-(--studio-danger)/12 px-4 text-sm font-medium text-(--studio-danger-fg) outline-none transition-colors hover:bg-(--studio-danger)/20 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-60 [&_svg]:size-4 [&_svg]:shrink-0";

export const LINK_BUTTON =
  "inline-flex items-center gap-1 rounded-md text-sm font-medium text-(--studio-accent-fg) underline-offset-4 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-3.5 [&_svg]:shrink-0";

const HEADINGS = { 3: "h3", 4: "h4" } as const;

export type ViewCardProps = {
  title: ReactNode;
  icon?: ReactNode;
  description?: ReactNode;
  /** Controls at the end of the header (buttons, a badge). */
  action?: ReactNode;
  headingLevel?: keyof typeof HEADINGS;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
};

/**
 * A titled glass card for one part of a stage output. The icon takes the stage colour of the
 * panel around it (`data-stage` → `--tone-fg`).
 */
export function ViewCard({
  title,
  icon,
  description,
  action,
  headingLevel = 4,
  className,
  bodyClassName,
  children,
}: ViewCardProps) {
  const id = useId();
  const Heading = HEADINGS[headingLevel];
  return (
    <GlassCard
      render={<section aria-labelledby={id} />}
      className={cn("grid min-w-0 content-start gap-4 p-4 sm:p-5", className)}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="grid min-w-0 gap-1">
          <Heading
            id={id}
            className="flex min-w-0 items-center gap-2 text-sm font-semibold tracking-tight break-words text-foreground [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-[var(--tone-fg,var(--muted-foreground))]"
          >
            {icon}
            {title}
          </Heading>
          {description && <div className="text-xs text-muted-foreground">{description}</div>}
        </div>
        {action}
      </div>
      <div className={cn("min-w-0", bodyClassName)}>{children}</div>
    </GlassCard>
  );
}

/** A pill in a tone (or a stage's colour): text stays at 4.5:1 on its own 12% tint. */
export function Chip({
  tone = "neutral",
  stage,
  title,
  mono = false,
  className,
  children,
}: {
  tone?: Tone;
  stage?: string;
  title?: string;
  mono?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      data-tone={stage ? undefined : tone}
      data-stage={stage}
      title={title}
      className={cn(
        "inline-flex min-h-6 max-w-full items-center gap-1 rounded-full border border-(--tone)/25 bg-(--tone)/12 px-2 py-0.5 text-xs font-medium break-words text-(--tone-fg) [&_svg]:size-3.5 [&_svg]:shrink-0",
        mono && "font-mono",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A note inside a stage view or the page: an icon, a title, optional text and an action. */
export function Callout({
  tone,
  icon: Icon,
  title,
  action,
  role,
  live = false,
  className,
  children,
}: {
  tone: Tone;
  icon: LucideIcon;
  title: ReactNode;
  action?: ReactNode;
  role?: "alert" | "status";
  /** Show a pulsing dot instead of the icon (something is running). */
  live?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div
      role={role}
      data-tone={tone}
      className={cn(
        "flex flex-wrap items-start gap-x-3 gap-y-2 rounded-2xl border border-(--tone)/25 bg-(--tone)/8 p-3.5 sm:p-4",
        className,
      )}
    >
      <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center text-(--tone-fg)">
        {live ? <PulseDot tone={tone} live /> : <Icon aria-hidden className="size-4" />}
      </span>
      <div className="grid min-w-0 flex-1 basis-56 gap-1 text-sm">
        <p className="font-medium break-words text-foreground">{title}</p>
        {children && <div className="break-words text-muted-foreground">{children}</div>}
      </div>
      {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
    </div>
  );
}

/** A stage status as a pill: its icon (a pulsing dot while running) and its name. */
export function StageStatusChip({ status }: { status: TimelineStatus }) {
  const t = useTranslations("stageStatus");
  const meta = statusMeta(status);
  const Icon = meta.icon;
  return (
    <Chip tone={meta.tone}>
      {meta.live ? <PulseDot tone={meta.tone} live size="sm" /> : <Icon aria-hidden />}
      {t(status)}
    </Chip>
  );
}
