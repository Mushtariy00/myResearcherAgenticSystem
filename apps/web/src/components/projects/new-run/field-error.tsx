"use client";

import { useTranslations } from "next-intl";
import { newRunFieldError } from "@/lib/new-run-schema";

/** A field's error code from the form, as a sentence (`wizard.errors.*`). */
export function FieldError({
  id,
  error,
}: {
  id?: string;
  error: { message?: string | undefined } | null | undefined;
}) {
  const t = useTranslations();
  const message = newRunFieldError(error);
  if (!message) {
    return null;
  }
  return (
    <p id={id} className="text-sm text-destructive">
      {t(message.key, message.values)}
    </p>
  );
}

/** `aria-describedby` for a field: its hint, and its error while there is one. */
export function describedBy(hintId: string | null, errorId: string, hasError: boolean): string {
  return [hintId, hasError ? errorId : null].filter(Boolean).join(" ");
}
