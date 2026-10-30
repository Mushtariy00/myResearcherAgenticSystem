import Link from "next/link";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { StudioMark } from "./studio-mark";

/**
 * The product name with the Studio mark, as a link. `collapsible` hides the words (for screen
 * readers they stay) when the sidebar is collapsed.
 */
export function StudioBrand({
  href,
  collapsible = false,
  className,
}: {
  href: string;
  collapsible?: boolean;
  className?: string;
}) {
  const t = useTranslations();
  return (
    <Link
      href={href}
      className={cn(
        "flex min-w-0 items-center gap-2.5 rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        className,
      )}
    >
      <StudioMark />
      <span
        className={cn(
          "grid min-w-0 leading-tight",
          collapsible && "studio-sidebar-label group-data-[sidebar=collapsed]/shell:sr-only",
        )}
      >
        <span className="truncate text-[0.8125rem] font-semibold tracking-tight text-foreground">
          {t("common.appName")}
        </span>
        <span className="text-[0.7rem] font-semibold tracking-[0.14em] text-(--studio-accent-fg) uppercase">
          {t("shell.version.studio")}
        </span>
      </span>
    </Link>
  );
}
