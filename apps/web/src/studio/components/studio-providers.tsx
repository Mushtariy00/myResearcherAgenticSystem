"use client";

import { MotionConfig } from "motion/react";
import { type ReactNode, useLayoutEffect } from "react";

/**
 * The client side of the Studio root:
 * - `<MotionConfig reducedMotion="user">`: motion drops movement for visitors who asked for
 *   reduced motion (fades remain).
 * - While a Studio page is open, <html> carries `data-ui="studio"` and the font classes, so
 *   menus, dialogs and toasts (portaled to <body>) use the Studio tokens and fonts too. Leaving
 *   Studio for a Classic page removes them again.
 */
export function StudioProviders({
  fontClassName,
  children,
}: {
  fontClassName: string;
  children: ReactNode;
}) {
  useLayoutEffect(() => {
    const html = document.documentElement;
    const classes = fontClassName.split(/\s+/).filter(Boolean);
    html.setAttribute("data-ui", "studio");
    html.classList.add(...classes);
    return () => {
      html.removeAttribute("data-ui");
      html.classList.remove(...classes);
    };
  }, [fontClassName]);

  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
