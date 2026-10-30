"use client";

import { useTranslations } from "next-intl";
import { useCallback } from "react";

export type MessageValues = Record<string, string | number | Date>;

/** next-intl's translator without the typed key list, for keys known only at run time. */
type LooseTranslator = {
  (key: string, values?: MessageValues): string;
  has(key: string): boolean;
};

/**
 * Looks up a message that another area of the app owns and may not have added yet, such as the
 * shared wizard field errors (`wizard.errors.*`, from `newRunFieldError`) or the project
 * settings errors (`project.settings.errors.*`). It returns null while the key does not exist,
 * so the caller can show Studio's own copy instead:
 *
 * ```ts
 * const optional = useOptionalMessage();
 * optional(error.key, error.values) ?? t(`wizard.errors.${error.code}`, error.values)
 * ```
 */
export function useOptionalMessage(): (key: string, values?: MessageValues) => string | null {
  const t = useTranslations() as unknown as LooseTranslator;
  return useCallback((key, values) => (t.has(key) ? t(key, values) : null), [t]);
}
