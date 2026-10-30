"use client";

import {
  ChevronUpIcon,
  CircleAlertIcon,
  EyeIcon,
  GitCompareArrowsIcon,
  LoaderCircleIcon,
  MessageSquareIcon,
  PencilLineIcon,
  RefreshCwIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { toast } from "sonner";
import type { StageOutputOut } from "@/client";
import { DemoBadge } from "@/components/shared/demo-badge";
import { type JsonParseResult, parseJson, toJsonText } from "@/components/shared/json-parse";
import { MAX_COMMENT_LENGTH, useApprovalDecision } from "@/hooks/use-approval-decision";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useStage } from "@/hooks/use-stage";
import { isDemoOutput } from "@/lib/stage-output";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/studio/components/effects/glass-card";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { stageAttr } from "@/studio/lib/stages";
import { ICON_BUTTON, OUTLINE_BUTTON } from "@/studio/lib/ui";
import { StudioConfirmDialog } from "./confirm-dialog";
import { ChangesPanel, EditPanel } from "./review-panels";
import { useRunPage } from "./run-context";
import { isRecord } from "./run-helpers";
import { Callout, Chip, DANGER_BUTTON, SMALL_BUTTON, TOGGLE_BUTTON } from "./run-ui";
import { useRunLabels } from "./use-run-labels";

type Panel = "changes" | "edit" | null;

/** Edited JSON for one version under review. */
type Draft = { outputId: string; text: string; result: JsonParseResult };

/** A draft that differs from the output: valid JSON to approve with, or text to fix first. */
type DraftState = "none" | "unchanged" | "changed" | "invalid";

function sameJson(left: unknown, right: unknown): boolean {
  return toJsonText(left, { sortKeys: true }) === toJsonText(right, { sortKeys: true });
}

function draftState(draft: Draft | null, output: StageOutputOut): DraftState {
  if (!draft) {
    return "none";
  }
  if (!draft.result.ok || !isRecord(draft.result.value)) {
    return "invalid";
  }
  return sameJson(draft.result.value, output.data) ? "unchanged" : "changed";
}

/**
 * The review dock for the output waiting for a decision (useApprovalDecision), sticky at the
 * bottom of the stage column and docked to the bottom of the screen on phones. It names the
 * version (and the Demo badge), opens the changes since the previous version or an editor to
 * approve with edits, takes a comment, and approves, requests changes (a comment is required)
 * or rejects (after a confirmation). As in Classic, a decision binds to the version on screen:
 * a 409 says the output changed, and a new version locks the buttons until it has been read.
 */
export function ApprovalDock() {
  const { runId, run, activeStage, showStage } = useRunPage();
  const t = useTranslations("studioRun.review");
  const tApproval = useTranslations("run.approval");
  const labels = useRunLabels();
  const errorMessage = useErrorMessage();
  const ids = useId();
  const commentRef = useRef<HTMLTextAreaElement>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [expanded, setExpanded] = useState(false);
  const [confirmReject, setConfirmReject] = useState(false);
  const [storedDraft, setDraft] = useState<Draft | null>(null);

  const approval = useApprovalDecision(run, {
    onDecided: (decision) => {
      // Approving the run's last stage finishes the run: there is no next stage to announce.
      const final = decision === "approve" && run?.awaiting_stage === run?.config.stages.at(-1);
      toast.success(final ? tApproval("sent.approveFinal") : tApproval(`sent.${decision}`));
      setDraft(null);
      setPanel(null);
    },
    onConflict: () => toast.warning(tApproval("conflictToast")),
    onError: (error) => {
      if (error.code === "decision.invalid_edit") {
        setPanel("edit");
        setExpanded(true);
      } else {
        toast.error(errorMessage(error));
      }
    },
  });
  const output = approval.output;
  const stage = approval.stage ?? "";
  const review = useStage(runId, stage, { outputId: output?.id ?? null });

  if (!output || !approval.canDecide) {
    return null;
  }

  const draft = storedDraft?.outputId === output.id ? storedDraft : null;
  const edits = draftState(draft, output);
  const stageName = labels.stage(stage);
  const { locked, pending, pendingDecision, commentMissing } = approval;
  const commentId = `${ids}-comment`;
  const hintId = `${ids}-hint`;
  const panelId = `${ids}-panel`;
  const titleId = `${ids}-title`;

  function togglePanel(next: Exclude<Panel, null>) {
    setPanel((current) => (current === next ? null : next));
    setExpanded(true);
    if (next === "edit" && !draft && output) {
      const text = toJsonText(output.data);
      setDraft({ outputId: output.id, text, result: parseJson(text) });
    }
  }

  function approve() {
    if (edits === "changed" && draft?.result.ok && isRecord(draft.result.value)) {
      approval.approveWithEdits(draft.result.value);
    } else if (edits !== "invalid") {
      approval.approve();
    }
  }

  function requestChanges() {
    if (approval.requestChanges() === "comment_required") {
      flushSync(() => setExpanded(true));
      commentRef.current?.focus();
    }
  }

  const sending = (decision: "approve" | "request_changes" | "reject") =>
    pending && pendingDecision === decision;

  return (
    <section
      aria-labelledby={titleId}
      data-stage={stageAttr(stage)}
      className={cn(
        "studio-glass studio-blur z-30 flex flex-col bg-(--studio-glass-strong) shadow-[inset_0_1px_0_0_var(--studio-glass-highlight),0_-12px_40px_-20px_var(--studio-glow)]",
        "fixed inset-x-0 bottom-0 max-h-[85dvh] rounded-t-2xl rounded-b-none border-x-0 border-b-0 pb-[env(safe-area-inset-bottom)]",
        "md:sticky md:bottom-4 md:inset-x-auto md:max-h-[calc(100dvh-6rem)] md:rounded-2xl md:border md:pb-0",
      )}
    >
      {panel && (
        <div
          id={panelId}
          className={cn(
            "min-h-0 shrink overflow-y-auto overscroll-contain border-b border-(--studio-glass-border) p-3 sm:p-4",
            // Collapsed on phones and on short desktop windows, where the open dock would cover
            // half of the output under review.
            expanded ? "block" : "hidden md:[@media(min-height:860px)]:block",
          )}
        >
          {panel === "changes" ? (
            <ChangesPanel stage={stage} output={output} review={review} />
          ) : (
            <EditPanel
              stage={stage}
              original={output.data}
              text={draft?.text ?? toJsonText(output.data)}
              result={draft?.result ?? { ok: true, value: output.data }}
              changed={edits === "changed" || edits === "invalid"}
              invalidEdit={approval.invalidEdit}
              onChange={(text, result) => setDraft({ outputId: output.id, text, result })}
              onDiscard={() => setDraft(null)}
            />
          )}
        </div>
      )}

      <div className="grid shrink-0 gap-3 p-3 sm:p-4">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
          <PulseDot tone="warning" />
          <h2 id={titleId} className="min-w-0 text-sm font-semibold break-words text-foreground">
            {tApproval("title", { stage: stageName })}
          </h2>
          <span className="text-xs text-muted-foreground tabular-nums">
            {t("version", { version: output.version })}
          </span>
          <DemoBadge demo={isDemoOutput(output)} degradedReason={output.degraded_reason} />
          {output.degraded && !isDemoOutput(output) && (
            <Chip tone="warning">{tApproval("degradedTitle")}</Chip>
          )}
          {edits === "changed" && <Chip tone="info">{t("edited")}</Chip>}
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={`${ids}-more`}
            onClick={() => setExpanded((value) => !value)}
            className={cn(ICON_BUTTON, "ml-auto -my-1 md:[@media(min-height:860px)]:hidden")}
          >
            <ChevronUpIcon
              aria-hidden
              className={cn(
                "transition-transform duration-200 motion-reduce:transition-none",
                !expanded && "rotate-180",
              )}
            />
            <span className="sr-only">{expanded ? t("collapse") : t("expand")}</span>
          </button>
        </div>

        {approval.conflict && !approval.updatedWhileOpen && (
          <Callout
            tone="warning"
            icon={CircleAlertIcon}
            role="alert"
            title={tApproval("conflictTitle")}
          >
            {tApproval("conflictDescription")}
          </Callout>
        )}
        {approval.updatedWhileOpen && (
          <Callout
            tone="info"
            icon={RefreshCwIcon}
            role="alert"
            title={tApproval("updatedTitle")}
            action={
              <button type="button" className={SMALL_BUTTON} onClick={approval.acknowledge}>
                {tApproval("updatedAcknowledge")}
              </button>
            }
          >
            {tApproval("updatedDescription", { version: output.version })}
          </Callout>
        )}

        <div
          id={`${ids}-more`}
          className={cn("gap-3", expanded ? "grid" : "hidden md:[@media(min-height:860px)]:grid")}
        >
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              aria-expanded={panel === "changes"}
              aria-controls={panelId}
              onClick={() => togglePanel("changes")}
              className={TOGGLE_BUTTON}
            >
              <GitCompareArrowsIcon aria-hidden />
              {t("changes")}
            </button>
            <button
              type="button"
              aria-expanded={panel === "edit"}
              aria-controls={panelId}
              onClick={() => togglePanel("edit")}
              className={TOGGLE_BUTTON}
            >
              <PencilLineIcon aria-hidden />
              {t("edit")}
            </button>
            {activeStage !== stage && (
              <button type="button" onClick={() => showStage(stage)} className={SMALL_BUTTON}>
                <EyeIcon aria-hidden />
                {t("show", { stage: stageName })}
              </button>
            )}
          </div>
          <div className="grid gap-1.5">
            <label htmlFor={commentId} className="text-xs font-medium text-foreground">
              {tApproval("comment")}
            </label>
            <textarea
              ref={commentRef}
              id={commentId}
              value={approval.comment}
              onChange={(event) => approval.setComment(event.target.value)}
              maxLength={MAX_COMMENT_LENGTH}
              rows={2}
              placeholder={tApproval("commentPlaceholder")}
              aria-invalid={commentMissing || undefined}
              aria-describedby={hintId}
              className="field-sizing-content max-h-40 min-h-16 w-full resize-y rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-(--studio-danger)/60 aria-invalid:ring-3 aria-invalid:ring-(--studio-danger)/20"
            />
            <p
              id={hintId}
              data-tone={commentMissing ? "danger" : undefined}
              className={cn(
                "text-xs",
                commentMissing ? "font-medium text-(--tone-fg)" : "text-muted-foreground",
              )}
            >
              {commentMissing ? tApproval("commentRequired") : tApproval("commentHint")}
            </p>
          </div>
        </div>

        {edits === "invalid" && (
          <p data-tone="danger" className="text-xs font-medium text-(--tone-fg)">
            {t("invalidJson")}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            className={cn(DANGER_BUTTON, "flex-1 sm:flex-none")}
            disabled={locked}
            aria-haspopup="dialog"
            onClick={() => setConfirmReject(true)}
          >
            {sending("reject") ? (
              <LoaderCircleIcon aria-hidden className="animate-spin motion-reduce:animate-none" />
            ) : (
              <ThumbsDownIcon aria-hidden />
            )}
            {sending("reject") ? tApproval("sending") : tApproval("reject")}
          </button>
          <button
            type="button"
            className={cn(
              OUTLINE_BUTTON,
              "flex-1 disabled:pointer-events-none disabled:opacity-60 sm:flex-none",
            )}
            disabled={locked}
            onClick={requestChanges}
          >
            {sending("request_changes") ? (
              <LoaderCircleIcon aria-hidden className="animate-spin motion-reduce:animate-none" />
            ) : (
              <MessageSquareIcon aria-hidden />
            )}
            {sending("request_changes") ? tApproval("sending") : tApproval("requestChanges")}
          </button>
          <ShimmerButton
            className="flex-1 sm:flex-none"
            disabled={locked || edits === "invalid"}
            onClick={approve}
          >
            {sending("approve") ? (
              <LoaderCircleIcon aria-hidden className="animate-spin motion-reduce:animate-none" />
            ) : (
              <ThumbsUpIcon aria-hidden />
            )}
            {sending("approve")
              ? tApproval("sending")
              : edits === "changed"
                ? t("approveWithEdits")
                : tApproval("approve")}
          </ShimmerButton>
        </div>
      </div>

      <StudioConfirmDialog
        open={confirmReject}
        onOpenChange={setConfirmReject}
        title={tApproval("rejectConfirmTitle")}
        description={tApproval("rejectConfirmDescription")}
        confirmLabel={tApproval("rejectConfirm")}
        cancelLabel={tApproval("keepReviewing")}
        onConfirm={() => {
          setConfirmReject(false);
          approval.reject();
        }}
      />
    </section>
  );
}

/** The output waiting for review, for people who may follow the run but not decide on it. */
export function AwaitingNotice() {
  const { view, activeStage, showStage } = useRunPage();
  const t = useTranslations("studioRun.review");
  const tApproval = useTranslations("run.approval");
  const labels = useRunLabels();
  const titleId = useId();
  const awaiting = view.awaiting;
  if (!awaiting) {
    return null;
  }
  const stageName = labels.stage(awaiting.stage);
  return (
    <GlassCard
      render={<section aria-labelledby={titleId} />}
      data-stage={stageAttr(awaiting.stage)}
      className="flex flex-wrap items-center gap-3 p-4"
    >
      <span
        aria-hidden
        data-tone="warning"
        className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-(--tone)/25 bg-(--tone)/12 text-(--tone-fg)"
      >
        <EyeIcon className="size-4" />
      </span>
      <div className="grid min-w-0 flex-1 basis-56 gap-0.5">
        <h2 id={titleId} className="text-sm font-semibold break-words text-foreground">
          {tApproval("titleReadOnly", { stage: stageName })}
        </h2>
        <p className="text-xs text-muted-foreground">{tApproval("readOnly")}</p>
      </div>
      {activeStage !== awaiting.stage && (
        <button type="button" onClick={() => showStage(awaiting.stage)} className={SMALL_BUTTON}>
          <EyeIcon aria-hidden />
          {t("show", { stage: stageName })}
        </button>
      )}
    </GlassCard>
  );
}
