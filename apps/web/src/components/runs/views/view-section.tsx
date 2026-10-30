"use client";

import { type ReactNode, useId } from "react";
import { cn } from "@/lib/utils";

/** A titled part of a stage view (an h3 under the stage's h2), optionally with actions. */
export function ViewSection({
  title,
  actions,
  children,
  className,
}: {
  title: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("grid min-w-0 content-start gap-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={id} className="text-sm font-semibold">
          {title}
        </h3>
        {actions}
      </div>
      {children}
    </section>
  );
}

/** Short values (datasets, metrics, subtopics) as pills, or `empty` when there are none. */
export function TagList({ items, empty }: { items: readonly string[]; empty: string }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item, index) => (
        <li
          // Generated lists may repeat a value.
          // biome-ignore lint/suspicious/noArrayIndexKey: the list never reorders
          key={index}
          className="inline-flex h-6 items-center rounded-full border bg-muted/40 px-2.5 text-xs break-all"
        >
          {item}
        </li>
      ))}
    </ul>
  );
}

/** Generated prose: paragraphs split on blank lines, line breaks kept, markup shown as text. */
export function Prose({ text, className }: { text: string; className?: string }) {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  return (
    <div className={cn("grid gap-3 leading-relaxed break-words", className)}>
      {paragraphs.map((paragraph, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: paragraphs are positional
        <p key={index} className="whitespace-pre-line">
          {paragraph}
        </p>
      ))}
    </div>
  );
}
