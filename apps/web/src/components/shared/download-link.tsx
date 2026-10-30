"use client";

import type { VariantProps } from "class-variance-authority";
import { DownloadIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatBytes } from "./format";
import { isSameOriginPath } from "./urls";

export type DownloadLinkProps = {
  /** A same-origin attachment URL (see `artifactUrl`, `paperFileUrl`); anything else renders nothing. */
  href: string;
  /** Suggested file name; the API's Content-Disposition header has the final say. */
  filename?: string;
  /** Shown after the label, e.g. "(1.2 MB)". */
  sizeBytes?: number;
  /** Visible label; default "Download". */
  children?: ReactNode;
  variant?: VariantProps<typeof buttonVariants>["variant"];
  size?: VariantProps<typeof buttonVariants>["size"];
  className?: string;
};

/**
 * A link to a file the API streams as an attachment. Only same-origin paths are accepted, so
 * a URL taken from generated content can never send the reviewer elsewhere.
 */
export function DownloadLink({
  href,
  filename,
  sizeBytes,
  children,
  variant = "outline",
  size = "sm",
  className,
}: DownloadLinkProps) {
  const t = useTranslations("shared.download");
  const format = useFormatter();
  if (!isSameOriginPath(href)) {
    return null;
  }
  return (
    <a
      href={href}
      download={filename ?? ""}
      data-slot="download-link"
      aria-label={children ? undefined : filename ? t("downloadFile", { filename }) : undefined}
      className={cn(buttonVariants({ variant, size }), className)}
    >
      <DownloadIcon aria-hidden />
      {children ?? t("download")}
      {sizeBytes !== undefined && (
        <span className="font-normal text-muted-foreground tabular-nums">
          ({formatBytes(sizeBytes, format)})
        </span>
      )}
    </a>
  );
}
