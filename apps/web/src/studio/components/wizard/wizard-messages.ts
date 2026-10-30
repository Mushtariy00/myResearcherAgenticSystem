"use client";

import { useTranslations } from "next-intl";
import { useCallback } from "react";
import { newRunFieldError } from "@/lib/new-run-schema";
import { useOptionalMessage } from "@/studio/lib/messages";

/**
 * The sentence for a wizard field error (`formState.errors.<field>`), or null without one. The
 * shared wording is `wizard.errors.<code>` (src/lib/new-run-schema.ts), added with the Classic
 * wizard; until a code has it, Studio's own copy (`studioWork.wizard.errors.<code>`) is shown.
 */
export function useWizardFieldError(): (
  error: { message?: string | undefined } | null | undefined,
) => string | null {
  const optional = useOptionalMessage();
  const t = useTranslations("studioWork.wizard.errors");
  return useCallback(
    (error) => {
      const field = newRunFieldError(error);
      if (!field) {
        return null;
      }
      return optional(field.key, field.values) ?? t(field.code, field.values);
    },
    [optional, t],
  );
}
