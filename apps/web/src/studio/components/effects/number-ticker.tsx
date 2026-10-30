"use client";

import { useInView, useMotionValue, useSpring } from "motion/react";
import { useLocale } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { useReducedMotionPreference } from "@/studio/hooks/use-media-query";
import { useMountedAfterHydration } from "@/studio/lib/hydration";

export type NumberTickerProps = {
  value: number;
  /** Where the count starts when the ticker first appears on the client. */
  from?: number;
  /** `Intl.NumberFormat` options (currency, percent, compact...). */
  format?: Intl.NumberFormatOptions;
  /** Defaults to the UI language. */
  locale?: string;
  /** Spring tuning: the default counts up in about a second without overshooting. */
  stiffness?: number;
  damping?: number;
  className?: string;
};

/**
 * A number that springs to its value when it scrolls into view, then to every new value. Digits
 * are tabular and formatted with `Intl.NumberFormat` for the UI language. The final value is
 * always in the markup: assistive technology reads it once (the moving digits are hidden from
 * it), an invisible copy reserves its width so nothing shifts while counting, and server-rendered
 * or reduced-motion tickers simply show it.
 */
export function NumberTicker({
  value,
  from = 0,
  format,
  locale: localeProp,
  stiffness = 110,
  damping = 26,
  className,
}: NumberTickerProps) {
  const appLocale = useLocale();
  const locale = localeProp ?? appLocale;
  const formatKey = JSON.stringify(format ?? {});
  // biome-ignore lint/correctness/useExhaustiveDependencies: `formatKey` stands for `format`
  const formatter = useMemo(() => new Intl.NumberFormat(locale, format), [locale, formatKey]);
  const reduced = useReducedMotionPreference();
  const clientMount = useMountedAfterHydration();
  const [start] = useState(() => (clientMount && !reduced ? from : value));
  const motionValue = useMotionValue(start);
  const spring = useSpring(motionValue, { stiffness, damping });
  const display = useRef<HTMLSpanElement>(null);
  const inView = useInView(display, { once: true, margin: "0px 0px -8% 0px" });
  // Counts move through whole numbers (never "7.998"); fractional targets keep their precision.
  const fractionDigits =
    format?.maximumFractionDigits ??
    (Number.isInteger(value) ? 0 : Math.min(2, (String(value).split(".")[1] ?? "").length));
  const target = useRef({ value, step: 10 ** fractionDigits });
  target.current = { value, step: 10 ** fractionDigits };

  useEffect(() => {
    const write = (latest: number) => {
      if (display.current) {
        const { step } = target.current;
        display.current.textContent = formatter.format(Math.round(latest * step) / step);
      }
    };
    write(spring.get());
    const unsubscribeChange = spring.on("change", write);
    // A spring settles within a tolerance of its target; show the exact value once it rests.
    const unsubscribeComplete = spring.on("animationComplete", () => write(target.current.value));
    return () => {
      unsubscribeChange();
      unsubscribeComplete();
    };
  }, [spring, formatter]);

  useEffect(() => {
    if (reduced) {
      motionValue.jump(value);
      spring.jump(value);
    } else if (inView) {
      motionValue.set(value);
    }
  }, [value, inView, reduced, motionValue, spring]);

  const finalText = formatter.format(value);
  return (
    <span className={cn("inline-grid tabular-nums", className)} data-reduced={reduced || undefined}>
      <span aria-hidden className="invisible col-start-1 row-start-1">
        {finalText}
      </span>
      <span aria-hidden ref={display} className="col-start-1 row-start-1">
        {formatter.format(start)}
      </span>
      <span className="sr-only">{finalText}</span>
    </span>
  );
}
