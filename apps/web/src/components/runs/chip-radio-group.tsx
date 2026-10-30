"use client";

import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type ChipOption = {
  value: string;
  /** Visible content of the chip. */
  label: ReactNode;
  /** Accessible name when the visible content is shorter (icons, abbreviations). */
  name?: string;
  /** Dims the chip (an outdated version, a filter with no matches); it stays selectable. */
  muted?: boolean;
};

/**
 * One choice out of a few, as a row of chips (a radio group: Tab reaches the checked chip,
 * arrow keys move between chips). Used for the paper filter and the version switcher.
 */
export function ChipRadioGroup({
  label,
  value,
  onValueChange,
  options,
  className,
}: {
  /** Accessible name of the group. */
  label: string;
  value: string | null;
  onValueChange: (value: string) => void;
  options: readonly ChipOption[];
  className?: string;
}) {
  return (
    <RadioGroup
      aria-label={label}
      value={value}
      onValueChange={(next) => onValueChange(String(next))}
      className={cn("flex flex-wrap gap-1.5", className)}
    >
      {options.map((option) => (
        <Radio.Root
          key={option.value}
          value={option.value}
          aria-label={option.name}
          className={cn(
            "inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-full border px-3 text-xs font-medium whitespace-nowrap outline-none select-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground [&_svg]:size-3.5 [&_svg]:shrink-0",
            option.muted && "text-muted-foreground",
          )}
        >
          {option.label}
        </Radio.Root>
      ))}
    </RadioGroup>
  );
}
