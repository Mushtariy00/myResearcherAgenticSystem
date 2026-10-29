/// <reference types="vite/client" />
/**
 * Test-only: every UI message file, and the messages of each locale merged the way
 * src/i18n/messages.ts merges them at runtime.
 */
import type { Locale } from "@/i18n/config";

type Tree = { [key: string]: string | Tree };

const files = import.meta.glob<Tree>("../../messages/*/*.json", { eager: true, import: "default" });

/** messages/<locale>/<area>.json contents, keyed by locale, then area. */
export const messageFiles: Record<string, Record<string, Tree>> = {};
for (const [path, content] of Object.entries(files)) {
  const match = /messages\/([^/]+)\/([^/]+)\.json$/.exec(path);
  if (!match?.[1] || !match[2]) {
    throw new Error(`Unexpected message file path: ${path}`);
  }
  messageFiles[match[1]] ??= {};
  (messageFiles[match[1]] as Record<string, Tree>)[match[2]] = content;
}

export function mergedMessages(locale: Locale): Tree {
  return Object.assign({}, ...Object.values(messageFiles[locale] ?? {}));
}

export const enMessages = mergedMessages("en");
export const koMessages = mergedMessages("ko");
