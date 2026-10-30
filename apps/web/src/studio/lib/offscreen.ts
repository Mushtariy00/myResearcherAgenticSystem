"use client";

import { type RefObject, useEffect } from "react";

/** Loops just outside the viewport keep running, so they never stall as they scroll in. */
const ROOT_MARGIN = "96px";

let observer: IntersectionObserver | null | undefined;

function sharedObserver(): IntersectionObserver | null {
  if (observer === undefined) {
    observer =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(
            (entries) => {
              for (const entry of entries) {
                entry.target.toggleAttribute("data-offscreen", !entry.isIntersecting);
              }
            },
            { rootMargin: ROOT_MARGIN },
          );
  }
  return observer;
}

/**
 * Pauses an element's CSS loops (its own animation, its pseudo-elements' and its children's)
 * while it is off screen. One IntersectionObserver serves every looping effect on the page: it
 * sets `data-offscreen`, which globals.css turns into `animation-play-state: paused`. No React
 * state changes, so nothing re-renders as the page scrolls. Without IntersectionObserver the
 * loops simply keep running.
 */
export function usePauseOffscreen(ref: RefObject<Element | null>, enabled = true): void {
  useEffect(() => {
    const element = ref.current;
    const shared = enabled ? sharedObserver() : null;
    if (!element || !shared) {
      return;
    }
    shared.observe(element);
    return () => {
      shared.unobserve(element);
      element.removeAttribute("data-offscreen");
    };
  }, [ref, enabled]);
}
