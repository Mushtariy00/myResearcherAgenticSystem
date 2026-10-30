import { cn } from "@/lib/utils";

/**
 * A loading placeholder with a soft sweep (still with reduced motion). Hidden from assistive
 * technology: give the region `aria-busy` and a `LoadingStatus` with the spoken label. Size it
 * like the content it stands for, so nothing moves when the data arrives.
 */
export function ShimmerSkeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("studio-skeleton rounded-lg", className)} />;
}

/** The spoken "Loading…" for a region of skeletons. */
export function LoadingStatus({ label }: { label: string }) {
  return (
    <span role="status" className="sr-only">
      {label}
    </span>
  );
}
