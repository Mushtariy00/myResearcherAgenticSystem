"use client";

import { useMemo } from "react";

/**
 * Stage output as indented JSON text. React escapes it, so markup or scripts inside LLM output
 * are shown as plain characters and never interpreted.
 */
export function JsonView({ value, label }: { value: unknown; label: string }) {
  const text = useMemo(() => JSON.stringify(value, null, 2) ?? "", [value]);
  return (
    <section
      aria-label={label}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users must be able to scroll it
      tabIndex={0}
      className="max-h-[32rem] overflow-auto rounded-lg border bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      <pre className="p-3 font-mono text-xs leading-relaxed break-words whitespace-pre-wrap">
        <code>{text}</code>
      </pre>
    </section>
  );
}
