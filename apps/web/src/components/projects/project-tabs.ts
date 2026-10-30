"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

/** The sections of a project page, in tab order; the first is the default. */
export const PROJECT_TABS = ["runs", "papers", "members", "settings"] as const;

export type ProjectTab = (typeof PROJECT_TABS)[number];

export const DEFAULT_PROJECT_TAB: ProjectTab = "runs";

export function projectTabOf(value: unknown): ProjectTab {
  return typeof value === "string" && (PROJECT_TABS as readonly string[]).includes(value)
    ? (value as ProjectTab)
    : DEFAULT_PROJECT_TAB;
}

/** A link to a project, opened on one of its tabs. */
export function projectHref(projectId: string, tab: ProjectTab = DEFAULT_PROJECT_TAB): string {
  const path = `/projects/${encodeURIComponent(projectId)}`;
  return tab === DEFAULT_PROJECT_TAB ? path : `${path}?tab=${tab}`;
}

/**
 * The open tab of a project page, kept in `?tab=` so a reload or a shared link opens the same
 * section. Switching tabs replaces the history entry (Back leaves the page rather than walking
 * through tabs) through the native History API, which Next.js syncs with useSearchParams
 * without asking the server again.
 */
export function useProjectTab(): [ProjectTab, (tab: ProjectTab) => void] {
  const searchParams = useSearchParams();
  const fromUrl = projectTabOf(searchParams.get("tab"));
  const [tab, setTab] = useState(fromUrl);
  // The URL changed some other way (back, forward, a link): follow it.
  const [urlTab, setUrlTab] = useState(fromUrl);
  if (fromUrl !== urlTab) {
    setUrlTab(fromUrl);
    setTab(fromUrl);
  }

  const select = useCallback((next: ProjectTab) => {
    setTab(next);
    const params = new URLSearchParams(window.location.search);
    params.set("tab", next);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, []);

  return [tab, select];
}
