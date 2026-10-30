"use client";

import { EyeIcon, EyeOffIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ComponentProps, useState } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** The shared Input, sized and tinted for Studio forms (44px tall, 10px radius, glass fill). */
export const STUDIO_INPUT =
  "h-11 rounded-[10px] border-(--studio-glass-border) bg-(--studio-glass) px-3.5 text-base shadow-[inset_0_1px_2px_0_oklch(0_0_0/0.06)] transition-[color,box-shadow,border-color] md:text-sm dark:bg-(--studio-glass)";

export function StudioInput({ className, ...props }: ComponentProps<"input">) {
  return <Input className={cn(STUDIO_INPUT, className)} {...props} />;
}

/** A password input with a show/hide toggle (a pressed-state button announced by name). */
export function PasswordInput({ className, ...props }: Omit<ComponentProps<"input">, "type">) {
  const t = useTranslations("studio.auth");
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <Input
        type={visible ? "text" : "password"}
        className={cn(STUDIO_INPUT, "pr-11", className)}
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((value) => !value)}
        aria-pressed={visible}
        aria-label={t("showPassword")}
        title={visible ? t("hidePassword") : t("showPassword")}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-[10px] text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {visible ? (
          <EyeOffIcon aria-hidden className="size-4" />
        ) : (
          <EyeIcon aria-hidden className="size-4" />
        )}
      </button>
    </div>
  );
}
