"use client";

import { useTranslations } from "next-intl";
import { useCallback } from "react";
import { errorMessageKey } from "@/lib/api-error";

/** Returns a function that turns any API failure into a translated sentence. */
export function useErrorMessage(): (error: unknown) => string {
  const t = useTranslations("errors");
  return useCallback((error: unknown) => t(errorMessageKey(error)), [t]);
}
