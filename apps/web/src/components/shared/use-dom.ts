"use client";

import {
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useState,
  useSyncExternalStore,
} from "react";

/**
 * Small browser hooks for the shared components. Each returns a server-safe value while
 * rendering on the server and hydrating (so markup always matches), then follows the browser.
 */

const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

function canMatchMedia(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function";
}

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!canMatchMedia()) {
        return () => {};
      }
      const list = window.matchMedia(query);
      list.addEventListener?.("change", onChange);
      return () => list.removeEventListener?.("change", onChange);
    },
    [query],
  );
  const getSnapshot = useCallback(
    () => canMatchMedia() && window.matchMedia(query).matches,
    [query],
  );
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}

export function useReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}

function subscribeToTheme(onChange: () => void): () => void {
  if (typeof document === "undefined" || typeof MutationObserver === "undefined") {
    return () => {};
  }
  // next-themes switches `.dark` on <html>; Studio marks <html> with data-ui="studio".
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class", "data-ui", "data-theme", "style"],
  });
  const list = canMatchMedia() ? window.matchMedia("(prefers-color-scheme: dark)") : undefined;
  list?.addEventListener?.("change", onChange);
  return () => {
    observer.disconnect();
    list?.removeEventListener?.("change", onChange);
  };
}

/** Whether the dark theme is on (both interfaces put `.dark` on <html>). */
export function useIsDark(): boolean {
  return useSyncExternalStore(
    subscribeToTheme,
    () => document.documentElement.classList.contains("dark"),
    () => false,
  );
}

/**
 * Changes whenever colours may have changed: light/dark, entering or leaving Studio, or the
 * system colour scheme. Components that copy CSS colours into a canvas re-read them on change.
 */
export function useThemeKey(): string {
  return useSyncExternalStore(
    subscribeToTheme,
    () => {
      const html = document.documentElement;
      const dark = canMatchMedia() && window.matchMedia("(prefers-color-scheme: dark)").matches;
      return `${html.className}|${html.getAttribute("data-ui") ?? ""}|${dark ? "dark" : "light"}`;
    },
    () => "server",
  );
}

/**
 * The element's content width in CSS pixels, kept up to date with a ResizeObserver; undefined
 * until measured (server, first render, or a browser without ResizeObserver).
 */
export function useElementWidth(ref: RefObject<HTMLElement | null>): number | undefined {
  const [width, setWidth] = useState<number>();
  useIsomorphicLayoutEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    const measured = element.getBoundingClientRect().width;
    if (measured > 0) {
      setWidth(Math.round(measured));
    }
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const next = entries[0]?.contentRect.width;
      if (next !== undefined && next > 0) {
        setWidth(Math.round(next));
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}
