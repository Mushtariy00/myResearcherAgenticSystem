"use client";

import { BracesIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { LiteratureOutput } from "@/client";
import { JsonView } from "@/components/shared/json-view";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { NarrowedOutput, RawOutput } from "@/lib/stage-output";
import { useLabels } from "../use-labels";
import { type CodingBase, CodingView } from "./coding-view";
import { ExperimentView } from "./experiment-view";
import { LiteratureView } from "./literature-view";
import { MethodView } from "./method-view";
import { WritingView } from "./writing-view";

/** Data that is not its stage's shape, as plain JSON with the reason. */
export function RawOutputView({ output }: { output: RawOutput }) {
  const t = useTranslations("run.raw");
  const labels = useLabels();
  const stage = labels.stage(output.stage);
  return (
    <div className="grid gap-3">
      <Alert role="note">
        <BracesIcon aria-hidden />
        <AlertTitle>{t(output.reason, { stage })}</AlertTitle>
        <AlertDescription>{t("description")}</AlertDescription>
      </Alert>
      <JsonView value={output.data} label={t("label", { stage })} />
    </div>
  );
}

export type StageOutputViewProps = {
  runId: string;
  /** The version on screen (artifacts are matched against it). */
  outputId: string;
  narrowed: NarrowedOutput;
  /** The literature output that method proposals and draft citations refer to. */
  literature: LiteratureOutput | null;
  /** For coding: the version or attempt to compare with. */
  codingBase?: CodingBase | null;
};

/** One stage output in its stage's view, or as JSON when it is not that stage's shape. */
export function StageOutputView({
  runId,
  outputId,
  narrowed,
  literature,
  codingBase,
}: StageOutputViewProps) {
  switch (narrowed.kind) {
    case "literature":
      return <LiteratureView data={narrowed.data} />;
    case "method":
      return <MethodView data={narrowed.data} literature={literature} />;
    case "coding":
      return (
        <CodingView runId={runId} outputId={outputId} data={narrowed.data} previous={codingBase} />
      );
    case "experiment":
      return <ExperimentView runId={runId} outputId={outputId} data={narrowed.data} />;
    case "writing":
      return (
        <WritingView
          runId={runId}
          outputId={outputId}
          data={narrowed.data}
          literature={literature}
        />
      );
    case "raw":
      return <RawOutputView output={narrowed} />;
  }
}
