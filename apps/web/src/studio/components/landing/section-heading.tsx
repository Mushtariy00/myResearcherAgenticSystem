import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Eyebrow, display title and lead paragraph of a landing section. */
export function SectionHeading({
  id,
  eyebrow,
  title,
  subtitle,
  align = "center",
  tone = "info",
}: {
  id: string;
  eyebrow: string;
  title: ReactNode;
  subtitle?: ReactNode;
  align?: "center" | "start";
  tone?: string;
}) {
  return (
    <div
      className={cn(
        "flex max-w-2xl flex-col gap-3",
        align === "center" ? "mx-auto items-center text-center" : "items-start text-left",
      )}
    >
      <p
        data-tone={tone}
        className="text-xs font-semibold tracking-[0.14em] text-(--tone-fg) uppercase"
      >
        {eyebrow}
      </p>
      <h2 id={id} className="studio-display text-3xl text-foreground sm:text-4xl">
        {title}
      </h2>
      {subtitle && (
        <p className="text-base text-pretty text-muted-foreground sm:text-lg">{subtitle}</p>
      )}
    </div>
  );
}
