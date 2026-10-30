import type { Locale } from "./config";

/**
 * UI messages live in one file per area (messages/<locale>/<area>.json), so features can be
 * built in parallel without editing the same file. Every top-level namespace belongs to exactly
 * one area file, and the files are merged shallowly. Adding an area means adding it here and in
 * types.d.ts.
 */
export const MESSAGE_AREAS = [
  "core",
  "shell",
  "dashboard",
  "projects",
  "wizard",
  "runs",
  "papers",
  "admin",
  "notifications",
  "profile",
  "studio",
  "studioRun",
  "studioWork",
] as const;

export type MessageArea = (typeof MESSAGE_AREAS)[number];

export async function loadMessages(locale: Locale): Promise<Record<string, unknown>> {
  const parts = await Promise.all(
    MESSAGE_AREAS.map(
      async (area) =>
        (await import(`../../messages/${locale}/${area}.json`)).default as Record<string, unknown>,
    ),
  );
  return Object.assign({}, ...parts);
}
