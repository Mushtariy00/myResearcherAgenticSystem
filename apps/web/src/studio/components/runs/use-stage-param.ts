"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

/** The query parameter naming the stage on screen: `/studio/runs/<id>?stage=method`. */
export const STAGE_PARAM = "stage";

type Choice = { url: string | null; stage: string | null };

/**
 * The stage the visitor chose, kept in the URL so a shared link opens the same stage. Choosing
 * replaces the history entry (tabs are not pages: Back leaves the run), and Next.js keeps
 * `useSearchParams` in sync with `history.replaceState`. When the URL changes on its own (Back,
 * Forward, a link to another stage of the same run), the URL wins over the last choice.
 */
export function useStageParam(): [string | null, (stage: string) => void] {
  const params = useSearchParams();
  const fromUrl = params?.get(STAGE_PARAM) ?? null;
  const [choice, setChoice] = useState<Choice>({ url: fromUrl, stage: fromUrl });
  let current = choice;
  if (choice.url !== fromUrl) {
    // Adjusts state while rendering (react.dev: "Storing information from previous renders").
    current = { url: fromUrl, stage: fromUrl };
    setChoice(current);
  }

  const choose = useCallback((stage: string) => {
    setChoice((previous) => ({ ...previous, stage }));
    const url = new URL(window.location.href);
    if (url.searchParams.get(STAGE_PARAM) === stage) {
      return;
    }
    url.searchParams.set(STAGE_PARAM, stage);
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, []);

  return [current.stage, choose];
}
