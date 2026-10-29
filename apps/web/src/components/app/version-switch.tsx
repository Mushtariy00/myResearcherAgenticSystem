"use client";

import { LayoutTemplateIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { buttonVariants } from "@/components/ui/button";
import { toClassicPath, toStudioPath, uiVersionOf } from "@/lib/ui-version";
import { cn } from "@/lib/utils";

/** Opens the current page in the other interface: Classic ⇄ Studio (same data, same API). */
export function VersionSwitch({ className }: { className?: string }) {
  const t = useTranslations("shell.version");
  const pathname = usePathname();
  const inStudio = uiVersionOf(pathname) === "studio";
  const label = inStudio ? t("switchToClassic") : t("switchToStudio");
  const Icon = inStudio ? LayoutTemplateIcon : SparklesIcon;

  return (
    <Link
      href={inStudio ? toClassicPath(pathname) : toStudioPath(pathname)}
      prefetch={false}
      title={label}
      aria-label={label}
      className={cn(buttonVariants({ variant: "ghost", size: "sm" }), className)}
    >
      <Icon aria-hidden />
      <span className="hidden md:inline">{label}</span>
    </Link>
  );
}
