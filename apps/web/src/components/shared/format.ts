import type { useFormatter } from "next-intl";

/** next-intl's formatter (locale-aware numbers and dates). */
export type Formatter = ReturnType<typeof useFormatter>;

/** First characters of a hash for display, keeping a `sha256:` style prefix. */
export function shortHash(value: string, length = 12): string {
  const colon = value.indexOf(":");
  const prefix = colon > 0 && colon < 10 ? value.slice(0, colon + 1) : "";
  const digest = value.slice(prefix.length);
  return digest.length > length ? `${prefix}${digest.slice(0, length)}…` : value;
}

/** File sizes in the largest unit that keeps the number at or above 1 (localised unit). */
export function formatBytes(bytes: number, format: Formatter): string {
  const units = ["byte", "kilobyte", "megabyte", "gigabyte"] as const;
  let value = Math.max(0, bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return format.number(value, {
    style: "unit",
    unit: units[unit],
    unitDisplay: "short",
    maximumFractionDigits: unit === 0 ? 0 : 1,
  });
}

/** A duration in seconds as seconds, minutes or hours (one decimal), in the UI language. */
export function formatDuration(seconds: number, format: Formatter): string {
  const value = Math.max(0, seconds);
  let amount = value;
  let unit: "second" | "minute" | "hour" = "second";
  if (value >= 3600) {
    amount = value / 3600;
    unit = "hour";
  } else if (value >= 60) {
    amount = value / 60;
    unit = "minute";
  }
  return format.number(amount, {
    style: "unit",
    unit,
    unitDisplay: "short",
    maximumFractionDigits: 1,
  });
}

/** Up to `max` author names joined with commas, and whether more were left out. */
export function authorNames(
  authors: readonly string[],
  max = 3,
): { names: string; truncated: boolean } {
  const kept = authors.filter((name) => name.trim().length > 0);
  return { names: kept.slice(0, max).join(", "), truncated: kept.length > max };
}
