"use client";

import type { VariantProps } from "class-variance-authority";
import { CheckIcon, CopyIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useState } from "react";
import { Button, type buttonVariants } from "@/components/ui/button";

export type CopyButtonProps = {
  /** The text put on the clipboard. */
  value: string;
  /** Accessible name and tooltip, e.g. "Copy the full code hash". Default: "Copy". */
  label?: string;
  /** Visible text next to the icon; without it the button is icon-only. */
  children?: ReactNode;
  variant?: VariantProps<typeof buttonVariants>["variant"];
  size?: VariantProps<typeof buttonVariants>["size"];
  className?: string;
};

/** Copies a value and confirms it (icon change plus a polite screen-reader announcement). */
export function CopyButton({
  value,
  label,
  children,
  variant = "ghost",
  size,
  className,
}: CopyButtonProps) {
  const t = useTranslations("shared.copy");
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state === "idle") {
      return;
    }
    const timer = window.setTimeout(() => setState("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  const name = label ?? t("copy");
  return (
    <>
      <Button
        type="button"
        variant={variant}
        size={size ?? (children ? "sm" : "icon-sm")}
        onClick={copy}
        aria-label={children ? undefined : name}
        title={name}
        data-slot="copy-button"
        data-state={state}
        className={className}
      >
        {state === "copied" ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
        {children}
      </Button>
      <span role="status" className="sr-only">
        {state === "copied" ? t("copied") : state === "failed" ? t("failed") : ""}
      </span>
    </>
  );
}
