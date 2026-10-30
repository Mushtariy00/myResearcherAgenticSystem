"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { PdfViewerProps } from "./pdf-viewer-types";

export type { PdfViewerProps } from "./pdf-viewer-types";

function PdfViewerPlaceholder() {
  return (
    <div className={cn("grid gap-0 overflow-hidden rounded-xl border bg-card")}>
      <div className="flex gap-2 border-b px-2 py-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-6 w-24" />
      </div>
      <div className="bg-muted/40 p-6">
        <Skeleton className="mx-auto h-[60vh] w-full max-w-2xl" />
      </div>
    </div>
  );
}

/**
 * A PDF with page navigation, zoom and fit-to-width, a text layer, and evidence quotes found
 * and highlighted on their pages (jumping to the active one). Keyboard: Page Up / Page Down
 * turn pages, + and − zoom, and the toolbar is one tab stop with arrow-key navigation.
 * react-pdf and PDF.js load on demand in the browser only.
 */
export const PdfViewer = dynamic<PdfViewerProps>(
  () => import("./pdf-viewer-impl").then((module) => module.PdfViewerImpl),
  { ssr: false, loading: () => <PdfViewerPlaceholder /> },
);
