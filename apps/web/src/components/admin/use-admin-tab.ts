"use client";

import { useCallback, useState } from "react";
import { type AdminTab, DEFAULT_ADMIN_TAB, isAdminTab } from "./admin-sections";

/**
 * The open admin section, mirrored in the URL (`?tab=`) without a navigation: the App Router
 * picks up `history.replaceState`, and the back button is not filled with tab switches.
 */
export function useAdminTab(initial: AdminTab): [AdminTab, (value: string) => void] {
  const [tab, setTab] = useState<AdminTab>(initial);

  const select = useCallback((value: string) => {
    if (!isAdminTab(value)) {
      return;
    }
    setTab(value);
    const url = new URL(window.location.href);
    if (value === DEFAULT_ADMIN_TAB) {
      url.searchParams.delete("tab");
    } else {
      url.searchParams.set("tab", value);
    }
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);

  return [tab, select];
}
