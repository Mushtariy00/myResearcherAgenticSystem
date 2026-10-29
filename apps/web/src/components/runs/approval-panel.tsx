"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CircleAlertIcon,
  MessageSquareIcon,
  RefreshCwIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { toast } from "sonner";
import type { Decision, RunDetail, StageOutputOut } from "@/client";
import { decideStageMutation, getRunQueryKey } from "@/client/@tanstack/react-query.gen";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useErrorMessage } from "@/hooks/use-error-message";
import { APPROVAL_CONFLICT_CODES, toApiError } from "@/lib/api-error";
import { JsonView } from "./json-view";
import { useLabels } from "./use-labels";

function OutputMeta({ output }: { output: StageOutputOut }) {
  const t = useTranslations("run.approval");
  const format = useFormatter();
  return (
    <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
      <div className="flex gap-1">
        <dt>{t("version")}</dt>
        <dd className="font-medium text-foreground tabular-nums">{output.version}</dd>
      </div>
      <div className="flex gap-1">
        <dt>{t("model")}</dt>
        <dd className="font-medium text-foreground">{output.model ?? t("unknownModel")}</dd>
      </div>
      <div className="flex gap-1">
        <dt>{t("produced")}</dt>
        <dd className="font-medium text-foreground">
          {format.dateTime(new Date(output.created_at), {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </dd>
      </div>
      <div className="flex min-w-0 gap-1">
        <dt>{t("hash")}</dt>
        <dd className="truncate font-mono" title={output.sha256}>
          {output.sha256.slice(0, 12)}
        </dd>
      </div>
    </dl>
  );
}

export function DegradedWarning({ output }: { output: StageOutputOut }) {
  const t = useTranslations("run.approval");
  const labels = useLabels();
  if (!output.degraded) {
    return null;
  }
  return (
    <Alert variant="destructive">
      <TriangleAlertIcon aria-hidden />
      <AlertTitle>{t("degradedTitle")}</AlertTitle>
      <AlertDescription>
        <p>{t("degradedDescription")}</p>
        {output.degraded_reason && (
          <p className="mt-1">
            {t("degradedReason")}{" "}
            <span className="break-words">{labels.degradedReason(output.degraded_reason)}</span>
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}

/** The output waiting for review, for people who may look but not decide. */
export function AwaitingPreview({ run }: { run: RunDetail }) {
  const t = useTranslations("run.approval");
  const labels = useLabels();
  const output = run.awaiting;
  if (!output) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {t("titleReadOnly", { stage: labels.stage(run.awaiting_stage ?? "") })}
        </CardTitle>
        <CardDescription>{t("readOnly")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <DegradedWarning output={output} />
        <OutputMeta output={output} />
        <JsonView value={output.data} label={t("outputLabel")} />
      </CardContent>
    </Card>
  );
}

/**
 * Approve / request changes / reject the output waiting for review. The decision carries the
 * output id and sha256 the reviewer saw; if the output changed meanwhile, the API answers 409,
 * and if a new version arrives while the panel is open, the buttons stay locked until the
 * reviewer acknowledges it.
 */
export function ApprovalPanel({ run }: { run: RunDetail }) {
  const t = useTranslations("run.approval");
  const labels = useLabels();
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const ids = useId();
  const output = run.awaiting;
  const [comment, setComment] = useState("");
  const [commentMissing, setCommentMissing] = useState(false);
  const [confirmReject, setConfirmReject] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [seenHash, setSeenHash] = useState(output?.sha256 ?? "");

  const runKey = getRunQueryKey({ path: { run_id: run.id } });
  const decide = useMutation({
    ...decideStageMutation(),
    onSuccess: async (_data, variables) => {
      toast.success(t(`sent.${variables.body.decision}`));
      setComment("");
      setConflict(false);
      await queryClient.invalidateQueries({ queryKey: runKey });
    },
    onError: async (error) => {
      if (APPROVAL_CONFLICT_CODES.has(toApiError(error).code)) {
        setConflict(true);
        toast.warning(t("conflictToast"));
        await queryClient.invalidateQueries({ queryKey: runKey });
        return;
      }
      toast.error(errorMessage(error));
    },
  });

  if (!output) {
    return null;
  }

  const updatedWhileOpen = seenHash !== output.sha256;
  const locked = decide.isPending || updatedWhileOpen;

  function send(decision: Decision) {
    if (!output) {
      return;
    }
    const text = comment.trim();
    if (decision === "request_changes" && text.length === 0) {
      setCommentMissing(true);
      document.getElementById(`${ids}-comment`)?.focus();
      return;
    }
    setCommentMissing(false);
    decide.mutate({
      path: { run_id: run.id },
      body: { stage_output_id: output.id, sha256: output.sha256, decision, comment: text },
    });
  }

  return (
    <Card className="border-amber-500/40 ring-amber-500/20">
      <CardHeader>
        <CardTitle>{t("title", { stage: labels.stage(run.awaiting_stage ?? "") })}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {conflict && !updatedWhileOpen && (
          <Alert>
            <CircleAlertIcon aria-hidden />
            <AlertTitle>{t("conflictTitle")}</AlertTitle>
            <AlertDescription>{t("conflictDescription")}</AlertDescription>
          </Alert>
        )}
        {updatedWhileOpen && (
          <Alert>
            <RefreshCwIcon aria-hidden />
            <AlertTitle>{t("updatedTitle")}</AlertTitle>
            <AlertDescription>
              {t("updatedDescription", { version: output.version })}
            </AlertDescription>
            <AlertAction>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setSeenHash(output.sha256);
                  setConflict(false);
                }}
              >
                {t("updatedAcknowledge")}
              </Button>
            </AlertAction>
          </Alert>
        )}
        <DegradedWarning output={output} />
        <OutputMeta output={output} />
        <JsonView value={output.data} label={t("outputLabel")} />
        <div className="grid gap-2">
          <Label htmlFor={`${ids}-comment`}>{t("comment")}</Label>
          <Textarea
            id={`${ids}-comment`}
            value={comment}
            onChange={(event) => {
              setComment(event.target.value);
              if (commentMissing && event.target.value.trim()) {
                setCommentMissing(false);
              }
            }}
            maxLength={5000}
            rows={3}
            placeholder={t("commentPlaceholder")}
            aria-invalid={commentMissing || undefined}
            aria-describedby={`${ids}-comment-hint`}
          />
          <p
            id={`${ids}-comment-hint`}
            className={
              commentMissing ? "text-xs text-destructive" : "text-xs text-muted-foreground"
            }
          >
            {commentMissing ? t("commentRequired") : t("commentHint")}
          </p>
        </div>
      </CardContent>
      <CardFooter className="flex flex-wrap justify-end gap-2 border-t pt-4">
        <Button variant="destructive" disabled={locked} onClick={() => setConfirmReject(true)}>
          <ThumbsDownIcon aria-hidden />
          {t("reject")}
        </Button>
        <Button variant="outline" disabled={locked} onClick={() => send("request_changes")}>
          <MessageSquareIcon aria-hidden />
          {t("requestChanges")}
        </Button>
        <Button disabled={locked} onClick={() => send("approve")}>
          <ThumbsUpIcon aria-hidden />
          {decide.isPending ? t("sending") : t("approve")}
        </Button>
      </CardFooter>

      <AlertDialog open={confirmReject} onOpenChange={setConfirmReject}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("rejectConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("rejectConfirmDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("keepReviewing")}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                setConfirmReject(false);
                send("reject");
              }}
            >
              {t("rejectConfirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
