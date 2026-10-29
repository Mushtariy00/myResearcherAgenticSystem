export const locales = ["en", "ko"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

/** Cookie that stores the chosen UI language (no locale prefix in URLs). */
export const LOCALE_COOKIE = "NEXT_LOCALE";

/** The lab works in Korea; dates render in this zone on server and client alike. */
export const TIME_ZONE = "Asia/Seoul";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}

export function resolveLocale(cookieValue: string | undefined | null): Locale {
  return isLocale(cookieValue) ? cookieValue : defaultLocale;
}
