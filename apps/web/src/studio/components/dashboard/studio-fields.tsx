import { ChevronDownIcon, SearchIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Form controls of the Studio work pages (dashboard dialogs, the new-run wizard, project
 * settings, paper filters): glass fields with the 10px control radius, a 40px hit target and a
 * visible focus ring; invalid fields turn danger.
 */

export const STUDIO_FIELD =
  "h-10 w-full min-w-0 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-3 text-base text-foreground shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)] outline-none transition-colors placeholder:text-muted-foreground hover:border-[color-mix(in_oklch,var(--foreground)_22%,transparent)] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-(--studio-danger) aria-invalid:ring-(--studio-danger)/25 sm:text-sm";

export const STUDIO_LABEL = "text-sm font-medium text-foreground";

export const STUDIO_HINT = "text-xs text-pretty text-muted-foreground";

/**
 * A native select in the Studio field style (native, so it works the same with a keyboard, a
 * screen reader and a phone's own picker), with a chevron.
 */
export function StudioSelect({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <span className={cn("relative block min-w-0", className)}>
      <select {...props} className={cn(STUDIO_FIELD, "cursor-pointer appearance-none pr-9")}>
        {children}
      </select>
      <ChevronDownIcon
        aria-hidden
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </span>
  );
}

/** A search field with a leading magnifier (`type="search"`, so Escape clears it). */
export function StudioSearchInput({ className, ...props }: ComponentProps<"input">) {
  return (
    <span className={cn("relative block min-w-0", className)}>
      <SearchIcon
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
      />
      <input type="search" {...props} className={cn(STUDIO_FIELD, "pl-9")} />
    </span>
  );
}

/** A field's error message, linked to the field with `aria-describedby`. */
export function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} data-tone="danger" className="text-xs font-medium text-(--tone-fg)">
      {children}
    </p>
  );
}

/** A labelled group of controls (radio cards, checkboxes) with an optional hint and error. */
export function FieldGroup({
  legend,
  hint,
  error,
  errorId,
  className,
  children,
}: {
  legend: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  errorId?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <fieldset className={cn("grid min-w-0 gap-2", className)}>
      <legend className={cn(STUDIO_LABEL, "mb-2")}>{legend}</legend>
      {hint && <p className={cn(STUDIO_HINT, "-mt-1")}>{hint}</p>}
      {children}
      {error && errorId && <FieldError id={errorId}>{error}</FieldError>}
    </fieldset>
  );
}
