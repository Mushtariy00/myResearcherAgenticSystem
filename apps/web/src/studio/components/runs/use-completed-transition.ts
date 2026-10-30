"use client";

import { useState } from "react";
import type { RunStatus } from "@/client";

/**
 * Whether the run has just been completed on this page: true once the page has seen the run
 * unfinished and its status is now `completed`. Opening an already completed run never counts,
 * and a retried run that completes again counts again. Pair it with ConfettiBurst, which fires
 * on the false → true change only, and only while the page is visible.
 */
export function useCompletedTransition(status: RunStatus | undefined): boolean {
  const [sawUnfinished, setSawUnfinished] = useState(false);
  if (!sawUnfinished && status !== undefined && status !== "completed") {
    // Adjusts state while rendering (react.dev: "Storing information from previous renders").
    setSawUnfinished(true);
  }
  return sawUnfinished && status === "completed";
}
