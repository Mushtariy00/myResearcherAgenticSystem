"use client";

import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { useTheme } from "next-themes";
import { useSyncExternalStore, useTransition } from "react";
import { setLocale } from "@/i18n/actions";
import { isLocale, type Locale } from "@/i18n/config";

export const THEMES = ["light", "dark", "system"] as const;
export type ThemeChoice = (typeof THEMES)[number];

function isTheme(value: unknown): value is ThemeChoice {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

const subscribeNever = () => () => {};

/** False while server rendering and hydrating, true once mounted (next-themes reads storage). */
function useMounted(): boolean {
  return useSyncExternalStore(
    subscribeNever,
    () => true,
    () => false,
  );
}

/**
 * The language (a cookie, then a refresh re-renders the page in it) and the theme (next-themes,
 * stored in this browser), for the profile pages of both interfaces. `theme` is null until the
 * page is mounted, so server and client markup agree.
 */
export function usePreferences() {
  const locale = useLocale();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const mounted = useMounted();
  const [switching, startTransition] = useTransition();

  function chooseLocale(value: unknown) {
    if (!isLocale(value) || value === locale) {
      return;
    }
    startTransition(async () => {
      await setLocale(value);
      router.refresh();
    });
  }

  function chooseTheme(value: unknown) {
    if (isTheme(value)) {
      setTheme(value);
    }
  }

  return {
    locale: locale as Locale,
    chooseLocale,
    switchingLocale: switching,
    theme: mounted ? (isTheme(theme) ? theme : "system") : null,
    chooseTheme,
  };
}
