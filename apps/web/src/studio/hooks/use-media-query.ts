"use client";

import { MotionConfigContext } from "motion/react";
import { useCallback, useContext, useSyncExternalStore } from "react";

function canMatch(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function";
}

/**
 * Live result of a media query. It is `false` while server rendering and hydrating (so markup
 * always matches), then follows the browser, including later changes.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!canMatch()) {
        return () => {};
      }
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    [query],
  );
  const getSnapshot = useCallback(() => canMatch() && window.matchMedia(query).matches, [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
export const FINE_POINTER_QUERY = "(hover: hover) and (pointer: fine)";

/**
 * Whether decorative motion must stop: the visitor asked their system for reduced motion, or a
 * surrounding `<MotionConfig reducedMotion="always">` forces it. Studio's effects also stop in
 * CSS (`prefers-reduced-motion`), so the first paint is already still.
 */
export function useReducedMotionPreference(): boolean {
  const { reducedMotion } = useContext(MotionConfigContext);
  const prefersReduced = useMediaQuery(REDUCED_MOTION_QUERY);
  return reducedMotion === "always" || prefersReduced;
}

/** A mouse or trackpad that can hover (no tilt or spotlight effects on touch screens). */
export function useFinePointer(): boolean {
  return useMediaQuery(FINE_POINTER_QUERY);
}
