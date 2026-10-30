"use client";

import { CircleAlertIcon, GitCompareArrowsIcon, PencilLineIcon, Undo2Icon } from "lucide-react";
import { useTranslations } from "next-intl";
import type { StageOutputOut } from "@/client";
import { CodeDiff } from "@/components/shared/code-diff";
import { JsonDiff } from "@/components/shared/json-diff";
import { JsonEditor } from "@/components/shared/json-editor";
import type { JsonParseResult } from "@/components/shared/json-parse";
import type { InvalidEdit } from "@/hooks/use-approval-decision";
import type { StageView } from "@/hooks/use-stage";
import { outputAs } from "@/lib/stage-output";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { locationPath } from "./run-helpers";
import { Callout, SMALL_BUTTON } from "./run-ui";
import { useRunLabels } from "./use-run-labels";

/** Pydantic error types with a sentence of their own; others are named as they come. */
const KNOWN_ERROR_TYPES: Record<string, InvalidEditKind> = {
  missing: "missing",
  extra_forbidden: "extra",
  string_too_short: "tooShort",
  too_short: "tooShort",
  string_too_long: "tooLong",
  too_long: "tooLong",
  string_type: "type",
  int_type: "type",
  int_parsing: "type",
  float_type: "type",
  float_parsing: "type",
  bool_type: "type",
  bool_parsing: "type",
  list_type: "type",
  dict_type: "type",
  model_type: "type",
  literal_error: "choice",
  enum: "choice",
  greater_than: "range",
  greater_than_equal: "range",
  less_than: "range",
  less_than_equal: "range",
};

type InvalidEditKind = "missing" | "extra" | "tooShort" | "tooLong" | "type" | "choice" | "range";

/**
 * "Changes since the previous version" of the output under review: the version before it in
 * the same attempt (an edit), else the newest version of the attempt before (a revision after
 * a change request). Code is compared file by file, anything else as JSON.
 */
export function ChangesPanel({
  stage,
  output,
  review,
}: {
  stage: string;
  output: StageOutputOut;
  review: StageView;
}) {
  const t = useTranslations("studioRun.review");
  const previous = review.previous;
  if (review.query.isPending || (!review.selected && review.query.isFetching)) {
    return (
      <div aria-busy="true" className="grid gap-2">
        <LoadingStatus label={t("loadingChanges")} />
        <ShimmerSkeleton className="h-4 w-1/2" />
        <ShimmerSkeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }
  if (!previous) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <GitCompareArrowsIcon aria-hidden className="size-4 shrink-0" />
        {t("noPrevious")}
      </p>
    );
  }
  const before = review.previousNarrowed;
  const after = outputAs(stage, output);
  const title =
    previous.relation === "attempt"
      ? t("changesSinceAttempt", { attempt: previous.attempt.attempt })
      : t("changesSinceVersion", { version: previous.output.version });
  return (
    <div className="grid min-w-0 gap-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <GitCompareArrowsIcon aria-hidden className="size-4 text-(--tone-fg)" />
        {title}
      </h3>
      {before?.kind === "coding" && after.kind === "coding" ? (
        <CodeDiff before={before.data.files} after={after.data.files} height="22rem" />
      ) : (
        <JsonDiff
          before={previous.output.data}
          after={output.data}
          label={title}
          maxHeight="22rem"
        />
      )}
    </div>
  );
}

/**
 * "Edit before approving": the output as JSON, live parse errors, the edits as a diff, and
 * where the stage's schema refused the last edit (422 `decision.invalid_edit`).
 */
export function EditPanel({
  stage,
  original,
  text,
  result,
  changed,
  invalidEdit,
  onChange,
  onDiscard,
}: {
  stage: string;
  original: unknown;
  text: string;
  result: JsonParseResult;
  changed: boolean;
  invalidEdit: InvalidEdit | null;
  onChange: (text: string, result: JsonParseResult) => void;
  onDiscard: () => void;
}) {
  const t = useTranslations("studioRun.review");
  const labels = useRunLabels();
  return (
    <div className="grid min-w-0 gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="grid min-w-0 gap-0.5">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <PencilLineIcon aria-hidden className="size-4 text-(--tone-fg)" />
            {t("editTitle")}
          </h3>
          <p className="text-xs text-muted-foreground">{t("editHint")}</p>
        </div>
        {changed && (
          <button type="button" onClick={onDiscard} className={SMALL_BUTTON}>
            <Undo2Icon aria-hidden />
            {t("discard")}
          </button>
        )}
      </div>
      {invalidEdit && <InvalidEditAlert invalidEdit={invalidEdit} />}
      <JsonEditor
        value={text}
        onChange={onChange}
        label={t("editorLabel", { stage: labels.stage(stage) })}
        height="18rem"
      />
      {changed && result.ok && (
        <details className="group grid gap-2">
          <summary className="w-fit cursor-pointer rounded-md text-xs font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
            {t("yourChanges")}
          </summary>
          <JsonDiff
            before={original}
            after={result.value}
            label={t("yourChanges")}
            maxHeight="16rem"
          />
        </details>
      )}
    </div>
  );
}

/** Where the stage's schema refused an edit: the path in the output and what is wrong there. */
export function InvalidEditAlert({ invalidEdit }: { invalidEdit: InvalidEdit }) {
  const t = useTranslations("studioRun.review.invalidEdit");
  const tErrors = useTranslations("errors");
  const path = locationPath(invalidEdit.loc);
  const kind = KNOWN_ERROR_TYPES[invalidEdit.type];
  return (
    <Callout
      tone="danger"
      icon={CircleAlertIcon}
      role="alert"
      title={tErrors("decision.invalid_edit")}
    >
      <span className="grid gap-1">
        <span>
          {t("where")}{" "}
          <code className="rounded bg-(--studio-glass-strong) px-1 py-0.5 font-mono text-xs break-all text-foreground">
            {path || t("whole")}
          </code>
        </span>
        <span>{kind ? t(`kinds.${kind}`) : t("other", { type: invalidEdit.type })}</span>
      </span>
    </Callout>
  );
}
