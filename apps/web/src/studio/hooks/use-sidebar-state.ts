"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "studio.sidebar";
const CHANGE_EVENT = "studio:sidebar";

/** Used when localStorage is unavailable (private windows, blocked storage). */
let memory: boolean | null = null;

function read(): boolean {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored !== null) {
      return stored === "collapsed";
    }
  } catch {
    // Storage is blocked: fall back to this tab's memory.
  }
  return memory ?? false;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

/**
 * Runs before the shell paints on a full page load (an inline script right inside
 * `#studio-shell`), so a collapsed sidebar never flashes open. React then catches up through
 * `useSidebarCollapsed`, which reads the same key.
 */
export const SIDEBAR_SCRIPT = `try{if(localStorage.getItem(${JSON.stringify(STORAGE_KEY)})==="collapsed"){var s=document.getElementById("studio-shell");if(s)s.setAttribute("data-sidebar","collapsed")}}catch(e){}`;

/** Whether the desktop sidebar is collapsed, remembered in localStorage and synced across tabs. */
export function useSidebarCollapsed(): [boolean, (collapsed: boolean) => void] {
  const collapsed = useSyncExternalStore(subscribe, read, () => false);
  const setCollapsed = useCallback((value: boolean) => {
    memory = value;
    try {
      window.localStorage.setItem(STORAGE_KEY, value ? "collapsed" : "expanded");
    } catch {
      // Not persisted; `memory` keeps it for this tab.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);
  return [collapsed, setCollapsed];
}
