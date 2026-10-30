"use client";

import { FlaskConicalIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { DEMO_DEGRADED_REASONS, isKnownDegradedReason } from "@/lib/api-error";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent } from "./tooltip";

/** Content the API marks `demo: true`, or an output whose degraded reason is a demo reason. */
export function isDemoContent({
  demo,
  degradedReason,
}: {
  demo?: boolean | null;
  degradedReason?: string | null;
}): boolean {
  return (
    demo === true ||
    (typeof degradedReason === "string" && DEMO_DEGRADED_REASONS.has(degradedReason))
  );
}

export type DemoBadgeProps = {
  /** The API's `demo` flag on papers, artifacts, runs and the like. */
  demo?: boolean | null;
  /** A stage output's `degraded_reason`; demo reasons show the badge and explain why. */
  degradedReason?: string | null;
  className?: string;
};

/**
 * A "Demo" pill that renders only for demo content. Hovering or pressing it opens an
 * explanation (a popover, so touch and screen-reader users can read it too).
 */
export function DemoBadge({ demo, degradedReason, className }: DemoBadgeProps) {
  const t = useTranslations("shared.demo");
  const reasons = useTranslations("degradedReasons");
  if (!isDemoContent({ demo, degradedReason })) {
    return null;
  }
  const reason = isKnownDegradedReason(degradedReason) ? reasons(degradedReason) : null;
  return (
    <Popover.Root>
      <Popover.Trigger
        openOnHover
        delay={250}
        closeDelay={150}
        data-tone="warning"
        data-slot="demo-badge"
        className={cn(
          "inline-flex h-5 w-fit shrink-0 cursor-help items-center gap-1 rounded-full bg-(--tone)/15 px-2 text-xs font-medium whitespace-nowrap text-(--tone-fg) ring-1 ring-(--tone)/30 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-3",
          className,
        )}
      >
        <FlaskConicalIcon aria-hidden />
        {t("badge")}
      </Popover.Trigger>
      <PopoverContent>
        <Popover.Title className="font-medium">{t("title")}</Popover.Title>
        <Popover.Description className="text-xs text-muted-foreground">
          {t("description")}
        </Popover.Description>
        {reason && (
          <p className="text-xs">
            <span className="font-medium">{t("reason")}</span> {reason}
          </p>
        )}
      </PopoverContent>
    </Popover.Root>
  );
}
