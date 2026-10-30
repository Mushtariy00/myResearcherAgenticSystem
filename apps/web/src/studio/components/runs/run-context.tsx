"use client";

import { createContext, type ReactNode, use } from "react";
import type { LiteratureOutput, RunDetail } from "@/client";
import type { RunView } from "@/hooks/use-run-view";

/** What the paper sheet opens on. */
export type PaperTarget = {
  /** Null for a `[n]` citation that is not in the draft's reference list. */
  paperId: string | null;
  /** The literature output on screen (an older version, say); default: the run's newest. */
  literature?: LiteratureOutput | null;
  /** Opens the PDF at this evidence quote of the paper's analysis. */
  quote?: number;
  /** Opened from a `[n]` marker in the draft. */
  citationKey?: number;
};

export type RunPageValue = {
  runId: string;
  run: RunDetail;
  view: RunView;
  /** The stage whose output is on screen (`?stage=`, else the page's choice). */
  activeStage: string;
  /** Shows a stage's output (tabs). */
  selectStage: (stage: string) => void;
  /** Shows a stage's output and scrolls it into view (pipeline, dock, notices). */
  showStage: (stage: string) => void;
  openPaper: (target: PaperTarget) => void;
  /** The paper the sheet shows, if open. */
  openPaperId: string | null;
  /** Opens the retry dialog, optionally with a stage chosen. */
  openRetry: (stage?: string) => void;
  /** The run's newest literature output, for paper titles in later stages. */
  literature: LiteratureOutput | null;
};

const RunPageContext = createContext<RunPageValue | null>(null);

export function RunPageProvider({ value, children }: { value: RunPageValue; children: ReactNode }) {
  return <RunPageContext value={value}>{children}</RunPageContext>;
}

/** The run page's data and actions, for the components inside StudioRunPage. */
export function useRunPage(): RunPageValue {
  const value = use(RunPageContext);
  if (!value) {
    throw new Error("useRunPage must be used inside RunPageProvider");
  }
  return value;
}
