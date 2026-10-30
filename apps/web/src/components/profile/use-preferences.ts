"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { useChooseLocale } from "@/components/app/use-choose-locale";

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
 * The language (a cookie, then a refresh re-renders the page in it; also the language of the
 * user's emails) and the theme (next-themes, stored in this browser), for the profile pages of
 * both interfaces. `theme` is null until the page is mounted, so server and client markup agree.
 */
export function usePreferences() {
  const { locale, chooseLocale, switchingLocale } = useChooseLocale();
  const { theme, setTheme } = useTheme();
  const mounted = useMounted();

  function chooseTheme(value: unknown) {
    if (isTheme(value)) {
      setTheme(value);
    }
  }

  return {
    locale,
    chooseLocale,
    switchingLocale,
    theme: mounted ? (isTheme(theme) ? theme : "system") : null,
    chooseTheme,
  };
}
