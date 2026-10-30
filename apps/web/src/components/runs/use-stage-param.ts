"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

/** The search parameter that names the stage on screen (`/runs/<id>?stage=coding`). */
export const STAGE_PARAM = "stage";

type Picked = { seen: string | null; stage: string | null };

/**
 * The stage tab, kept in the URL so a link or a reload opens the same stage. Choosing a tab
 * replaces the URL (switching tabs adds no history entries); when the URL changes from elsewhere
 * (a link to another stage of this run, back or forward), the URL wins.
 */
export function useStageParam(): [string | null, (stage: string) => void] {
  const fromUrl = useSearchParams().get(STAGE_PARAM);
  const [picked, setPicked] = useState<Picked>({ seen: fromUrl, stage: fromUrl });
  let current = picked;
  if (picked.seen !== fromUrl) {
    // Adjusts state while rendering (react.dev: "Storing information from previous renders").
    current = { seen: fromUrl, stage: fromUrl };
    setPicked(current);
  }

  const select = useCallback((stage: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set(STAGE_PARAM, stage);
    // Next.js syncs its router (and useSearchParams) with the native history API.
    window.history.replaceState(null, "", url);
    setPicked((previous) => ({ ...previous, stage }));
  }, []);

  return [current.stage, select];
}
