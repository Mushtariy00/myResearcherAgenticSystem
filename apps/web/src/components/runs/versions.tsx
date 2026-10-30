"use client";

import {
  CircleCheckIcon,
  CircleSlashIcon,
  CircleXIcon,
  EyeIcon,
  MessageSquareIcon,
  PencilIcon,
  RotateCcwIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import type { ApprovalOut, Decision } from "@/client";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { StageView } from "@/hooks/use-stage";
import type { VersionRef } from "@/lib/stage-output";
import { ChipRadioGroup } from "./chip-radio-group";
import { DegradedWarning, OutputMeta } from "./output-notes";
import { useLabels } from "./use-labels";

const DECISION_ICONS: Record<Decision, ReactNode> = {
  approve: <CircleCheckIcon aria-hidden />,
  request_changes: <RotateCcwIcon aria-hidden />,
  reject: <CircleXIcon aria-hidden />,
};

/** "Attempt 2, version 1: approved by Alice, edited by Bob": what a version chip stands for. */
function useVersionName() {
  const t = useTranslations("run.versions");
  const labels = useLabels();
  return (ref: VersionRef, underReview: boolean): string => {
    const parts: string[] = [];
    if (underReview) {
      parts.push(t("underReview"));
    }
    if (ref.output.approval) {
      parts.push(
        t("decidedBy", {
          decision: labels.decision(ref.output.approval.decision),
          name: ref.output.approval.actor_name ?? t("someone"),
        }),
      );
    }
    if (ref.output.edited_by) {
      parts.push(t("editedBy", { name: ref.output.edited_by_name ?? t("someone") }));
    }
    if (ref.attempt.status === "invalidated") {
      parts.push(t("outdated"));
    }
    const name = t("name", { attempt: ref.attempt.attempt, version: ref.output.version });
    return parts.length > 0 ? `${name}: ${parts.join(", ")}` : name;
  };
}

/**
 * Picks one version of a stage's outputs: every version of every attempt, oldest first, each
 * marked with its decision, edit, review or outdated state. Picking the newest follows new
 * versions again.
 */
export function VersionSwitcher({
  view,
  underReviewId,
}: {
  view: StageView;
  /** The output waiting for a decision, when it belongs to this stage. */
  underReviewId?: string | null;
}) {
  const t = useTranslations("run.versions");
  const versionName = useVersionName();
  const latestId = view.current?.output.id ?? null;
  const selectedId = view.selected?.output.id ?? latestId;
  return (
    <ChipRadioGroup
      label={t("label")}
      value={selectedId}
      onValueChange={(outputId) => view.select(outputId === latestId ? null : outputId)}
      options={view.versions.map((ref) => {
        const underReview = ref.output.id === underReviewId;
        const decision = ref.output.approval?.decision;
        return {
          value: ref.output.id,
          name: versionName(ref, underReview),
          muted: ref.attempt.status === "invalidated",
          label: (
            <>
              {t("short", { attempt: ref.attempt.attempt, version: ref.output.version })}
              {underReview && <EyeIcon aria-hidden />}
              {decision && DECISION_ICONS[decision]}
              {ref.output.edited_by && <PencilIcon aria-hidden />}
              {ref.attempt.status === "invalidated" && <CircleSlashIcon aria-hidden />}
            </>
          ),
        };
      })}
    />
  );
}

function DecisionNote({ approval }: { approval: ApprovalOut }) {
  const t = useTranslations("run.versions");
  const labels = useLabels();
  const format = useFormatter();
  return (
    <div className="grid gap-1 rounded-lg border bg-muted/30 px-3 py-2 text-sm">
      <p className="flex flex-wrap items-center gap-x-1.5 [&_svg]:size-4">
        {DECISION_ICONS[approval.decision]}
        <span className="font-medium">
          {t("decidedBy", {
            decision: labels.decision(approval.decision),
            name: approval.actor_name ?? t("someone"),
          })}
        </span>
        <time dateTime={approval.at} className="text-xs text-muted-foreground">
          {format.dateTime(new Date(approval.at), { dateStyle: "medium", timeStyle: "short" })}
        </time>
      </p>
      {approval.comment && (
        <blockquote className="border-l-2 pl-3 break-words whitespace-pre-line text-muted-foreground">
          {approval.comment}
        </blockquote>
      )}
    </div>
  );
}

/**
 * Where a version comes from: attempt, version, model, when, who edited it, the decision on
 * it, the feedback that started its attempt, and whether a retry made it outdated.
 */
export function VersionDetails({ version }: { version: VersionRef }) {
  const t = useTranslations("run.versions");
  const { attempt, output } = version;
  return (
    <div className="grid gap-3">
      <OutputMeta
        output={output}
        attempt={attempt.attempt}
        editedBy={output.edited_by ? (output.edited_by_name ?? "") : null}
      />
      {attempt.status === "invalidated" && (
        <Alert role="note">
          <CircleSlashIcon aria-hidden />
          <AlertTitle>{t("outdatedTitle")}</AlertTitle>
          <AlertDescription>{t("outdatedDescription")}</AlertDescription>
        </Alert>
      )}
      {attempt.feedback && attempt.attempt > 1 && (
        <div className="flex items-start gap-2 text-sm">
          <MessageSquareIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <p className="min-w-0 break-words">
            <span className="font-medium">{t("feedback")}</span>{" "}
            <span className="whitespace-pre-line text-muted-foreground">{attempt.feedback}</span>
          </p>
        </div>
      )}
      {output.approval && <DecisionNote approval={output.approval} />}
      <DegradedWarning output={output} />
    </div>
  );
}
