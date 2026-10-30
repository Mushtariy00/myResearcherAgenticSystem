import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { SpotlightCard } from "./spotlight-card";

/**
 * A feature grid: one column on phones, two on tablets, six tracks on desktop so cards can span
 * 2, 3 or 4 of them (pass the span in `className`, e.g. `lg:col-span-4`).
 */
export function BentoGrid({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <ul className={cn("grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-6", className)}>
      {children}
    </ul>
  );
}

export type BentoCardProps = {
  icon: LucideIcon;
  title: ReactNode;
  description: ReactNode;
  /** Grid placement, e.g. `sm:col-span-2 lg:col-span-4`. */
  className?: string;
  /** `data-stage` or `data-tone` value colouring the icon chip (see globals.css). */
  stage?: string;
  tone?: string;
  /** A small visual under the text (chips, a mini graph). */
  children?: ReactNode;
  /** Highlight colour of the spotlight (any CSS colour). */
  spotlightColor?: string;
};

export function BentoCard({
  icon: Icon,
  title,
  description,
  className,
  stage,
  tone,
  children,
  spotlightColor,
}: BentoCardProps) {
  return (
    <li className={cn("min-w-0", className)}>
      <SpotlightCard
        interactive={false}
        spotlightColor={spotlightColor}
        className="flex h-full flex-col gap-4 p-6"
      >
        <span
          aria-hidden
          data-stage={stage}
          data-tone={stage ? undefined : (tone ?? "info")}
          className="flex size-10 items-center justify-center rounded-xl border border-(--tone)/25 bg-(--tone)/12 text-(--tone-fg)"
        >
          <Icon className="size-5" />
        </span>
        <div className="grid gap-1.5">
          <h3 className="text-base font-semibold tracking-tight text-foreground">{title}</h3>
          <p className="text-sm leading-relaxed text-pretty text-muted-foreground">{description}</p>
        </div>
        {children && <div className="mt-auto pt-2">{children}</div>}
      </SpotlightCard>
    </li>
  );
}
