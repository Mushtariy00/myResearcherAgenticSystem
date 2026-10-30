"use client";

import { Tabs } from "@base-ui/react/tabs";
import {
  CircleAlertIcon,
  MessageSquareIcon,
  PencilIcon,
  RefreshCwIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useId, useMemo, useState } from "react";
import { toast } from "sonner";
import type { LiteratureOutput, RunDetail, StageOutputOut } from "@/client";
import { CodeDiff } from "@/components/shared/code-diff";
import { JsonDiff } from "@/components/shared/json-diff";
import { JsonEditor } from "@/components/shared/json-editor";
import { type JsonParseResult, parseJson, toJsonText } from "@/components/shared/json-parse";
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
import {
  type ApprovalDecision,
  type InvalidEdit,
  MAX_COMMENT_LENGTH,
  useApprovalDecision,
} from "@/hooks/use-approval-decision";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useStage } from "@/hooks/use-stage";
import { type DiffBase, type NarrowedOutput, outputAs } from "@/lib/stage-output";
import { cn } from "@/lib/utils";
import { DegradedWarning, DemoNotice, OutputMeta } from "./output-notes";
import { formatFieldPath, literatureOf } from "./run-data";
import { useLabels } from "./use-labels";
import { StageOutputView } from "./views/stage-output-view";

export { DegradedWarning } from "./output-notes";

const MODES = ["preview", "changes", "edit"] as const;
type ReviewMode = (typeof MODES)[number];

/** Tab panels take focus (Tab from the tab list), so they keep a visible focus ring. */
const PANEL_CLASS = "mt-4 rounded-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

function isMode(value: unknown): value is ReviewMode {
  return typeof value === "string" && (MODES as readonly string[]).includes(value);
}

/** Pydantic error types that have a translated explanation under `run.approval.issues`. */
const ISSUE_TYPES = [
  "missing",
  "extra_forbidden",
  "string_type",
  "string_too_short",
  "string_too_long",
  "too_short",
  "too_long",
  "int_type",
  "float_type",
  "bool_type",
  "list_type",
  "dict_type",
  "model_type",
  "literal_error",
  "greater_than_equal",
  "less_than_equal",
  "value_error",
  "unknown_stage",
] as const;
type IssueType = (typeof ISSUE_TYPES)[number];

function isIssueType(value: string): value is IssueType {
  return (ISSUE_TYPES as readonly string[]).includes(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The reviewer's JSON edit and the version (sha256) it started from. */
type EditDraft = { baseSha: string; text: string };

type EditState = {
  text: string;
  parsed: JsonParseResult;
  /** The edit as an object, once the text is valid JSON of one. */
  edited: Record<string, unknown> | null;
  /** The edit says something else than the output (key order does not count). */
  changed: boolean;
  /** A newer version arrived after the edit started from an older one. */
  stale: boolean;
};

function editState(output: StageOutputOut, draft: EditDraft | null): EditState {
  if (draft === null) {
    return {
      text: toJsonText(output.data),
      parsed: { ok: true, value: output.data },
      edited: output.data,
      changed: false,
      stale: false,
    };
  }
  const parsed = parseJson(draft.text);
  const edited = parsed.ok && isRecord(parsed.value) ? parsed.value : null;
  return {
    text: draft.text,
    parsed,
    edited,
    changed:
      edited !== null &&
      toJsonText(edited, { sortKeys: true }) !== toJsonText(output.data, { sortKeys: true }),
    stale: draft.baseSha !== output.sha256,
  };
}

function withoutFiles(data: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(data).filter(([key]) => key !== "files"));
}

function ModeTab({ value, children }: { value: ReviewMode; children: ReactNode }) {
  return (
    <Tabs.Tab
      value={value}
      className="-mb-px inline-flex h-9 items-center gap-1.5 border-b-2 border-transparent px-3 text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 data-active:border-primary data-active:text-foreground [&_svg]:size-4"
    >
      {children}
    </Tabs.Tab>
  );
}

/** What changed since the version or attempt before: the code diff for coding, else JSON. */
function ChangesView({
  previous,
  previousNarrowed,
  narrowed,
  output,
}: {
  previous: DiffBase;
  previousNarrowed: NarrowedOutput | null;
  narrowed: NarrowedOutput;
  output: StageOutputOut;
}) {
  const t = useTranslations("run.approval");
  const title =
    previous.relation === "version"
      ? t("changesSinceVersion", { version: previous.output.version })
      : t("changesSinceAttempt", { attempt: previous.attempt.attempt });
  if (narrowed.kind === "coding" && previousNarrowed?.kind === "coding") {
    return (
      <div className="grid gap-4">
        <p className="text-sm font-medium">{title}</p>
        <CodeDiff before={previousNarrowed.data.files} after={narrowed.data.files} />
        <div className="grid gap-2">
          <p className="text-sm font-medium">{t("otherChanges")}</p>
          <JsonDiff
            before={withoutFiles(previousNarrowed.data)}
            after={withoutFiles(narrowed.data)}
            label={t("otherChanges")}
          />
        </div>
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      <p className="text-sm font-medium">{title}</p>
      <JsonDiff before={previous.output.data} after={output.data} label={title} />
    </div>
  );
}

/** Where an approve-with-edits failed the stage's schema (422 `decision.invalid_edit`). */
function InvalidEditAlert({ edit, stage }: { edit: InvalidEdit; stage: string }) {
  const t = useTranslations("run.approval");
  const reason = isIssueType(edit.type)
    ? t(`issues.${edit.type}`)
    : t("issues.other", { type: edit.type });
  return (
    <Alert variant="destructive">
      <CircleAlertIcon aria-hidden />
      <AlertTitle>{t("invalidEditTitle", { stage })}</AlertTitle>
      <AlertDescription>
        {edit.loc.length > 0
          ? t.rich("invalidEditAt", {
              path: formatFieldPath(edit.loc),
              reason,
              field: (chunks) => (
                <code className="rounded bg-destructive/10 px-1 font-mono text-xs">{chunks}</code>
              ),
            })
          : t("invalidEditWhole", { reason })}
      </AlertDescription>
    </Alert>
  );
}

function EditOutput({
  stage,
  output,
  edit,
  onEdit,
  onReset,
  approval,
}: {
  stage: string;
  output: StageOutputOut;
  edit: EditState;
  onEdit: (text: string) => void;
  onReset: () => void;
  approval: ApprovalDecision;
}) {
  const t = useTranslations("run.approval");
  const labels = useLabels();
  const stageName = labels.stage(stage);
  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">{t("editHint", { stage: stageName })}</p>
      {edit.stale && (
        <Alert>
          <RefreshCwIcon aria-hidden />
          <AlertTitle>{t("staleEditTitle")}</AlertTitle>
          <AlertDescription>
            {t("staleEditDescription", { version: output.version })}
          </AlertDescription>
          <AlertAction>
            <Button size="sm" variant="outline" onClick={onReset}>
              {t("staleEditReset", { version: output.version })}
            </Button>
          </AlertAction>
        </Alert>
      )}
      <JsonEditor
        value={edit.text}
        onChange={(text) => onEdit(text)}
        label={t("editorLabel", { stage: stageName })}
      />
      {edit.parsed.ok && edit.edited === null && (
        <p className="text-xs text-destructive">{t("notObject")}</p>
      )}
      {approval.invalidEdit && <InvalidEditAlert edit={approval.invalidEdit} stage={stageName} />}
      <div className="grid gap-2">
        <p className="text-sm font-medium">{t("yourChanges")}</p>
        {edit.changed && edit.edited ? (
          <JsonDiff before={output.data} after={edit.edited} label={t("yourChanges")} />
        ) : (
          <p className="text-sm text-muted-foreground">{t("noEdits")}</p>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {edit.changed && (
          <Button variant="ghost" size="sm" onClick={onReset}>
            {t("discardEdits")}
          </Button>
        )}
        <Button
          disabled={!edit.changed || edit.stale || approval.locked}
          onClick={() => {
            if (edit.edited) {
              approval.approveWithEdits(edit.edited);
            }
          }}
        >
          <PencilIcon aria-hidden />
          {approval.pendingDecision === "approve" ? t("sending") : t("approveEdited")}
        </Button>
      </div>
    </div>
  );
}

/**
 * The output waiting for review, rendered with its stage's view, with what changed since the
 * version or attempt before. Reviewers who may decide also get the JSON editor, the comment and
 * the decisions; everyone else sees the same preview read-only.
 */
function ReviewCard({
  run,
  literature,
  decide,
}: {
  run: RunDetail;
  literature?: LiteratureOutput | null;
  decide: boolean;
}) {
  const t = useTranslations("run.approval");
  const labels = useLabels();
  const errorMessage = useErrorMessage();
  const ids = useId();
  const [confirmReject, setConfirmReject] = useState(false);
  const [mode, setMode] = useState<ReviewMode>("preview");
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const approval = useApprovalDecision(run, {
    onDecided: (decision, { edited }) => {
      toast.success(edited ? t("sentEdited") : t(`sent.${decision}`));
      if (edited) {
        setDraft(null);
      }
    },
    onConflict: () => toast.warning(t("conflictToast")),
    onError: (error) => toast.error(errorMessage(error)),
  });
  const { output, stage, comment, commentMissing, conflict, updatedWhileOpen, locked } = approval;
  const view = useStage(run.id, stage, { outputId: output?.id ?? null });
  const papersFrom = useMemo(
    () => (literature === undefined ? literatureOf(run) : literature),
    [literature, run],
  );
  const edit = useMemo(() => (output ? editState(output, draft) : null), [output, draft]);

  if (!output || stage === null || !edit) {
    return null;
  }

  const stageName = labels.stage(stage);
  const narrowed = view.narrowed ?? outputAs(stage, output);
  const previous = view.previous;
  const shownMode: ReviewMode =
    (mode === "changes" && !previous) || (mode === "edit" && !decide) ? "preview" : mode;

  function requestChanges() {
    if (approval.requestChanges() === "comment_required") {
      document.getElementById(`${ids}-comment`)?.focus();
    }
  }

  const sendingLabel = (decision: "approve" | "request_changes" | "reject", label: string) =>
    approval.pendingDecision === decision ? t("sending") : label;

  return (
    <Card data-slot="review-card" className={cn(decide && "border-amber-500/40 ring-amber-500/30")}>
      <CardHeader>
        <CardTitle>
          <h3>
            {decide ? t("title", { stage: stageName }) : t("titleReadOnly", { stage: stageName })}
          </h3>
        </CardTitle>
        <CardDescription>{decide ? t("description") : t("readOnly")}</CardDescription>
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
              <Button size="sm" variant="outline" onClick={approval.acknowledge}>
                {t("updatedAcknowledge")}
              </Button>
            </AlertAction>
          </Alert>
        )}
        <OutputMeta output={output} attempt={view.selected?.attempt.attempt} />
        <DemoNotice output={output} />
        <DegradedWarning output={output} />
        {view.selected?.attempt.feedback && (
          <p className="flex items-start gap-2 text-sm">
            <MessageSquareIcon
              aria-hidden
              className="mt-0.5 size-4 shrink-0 text-muted-foreground"
            />
            <span className="min-w-0 break-words">
              <span className="font-medium">{t("answersFeedback")}</span>{" "}
              <span className="whitespace-pre-line text-muted-foreground">
                {view.selected.attempt.feedback}
              </span>
            </span>
          </p>
        )}
        <Tabs.Root
          value={shownMode}
          onValueChange={(value) => setMode(isMode(value) ? value : "preview")}
        >
          <Tabs.List aria-label={t("views")} className="flex flex-wrap gap-1 border-b">
            <ModeTab value="preview">{t("preview")}</ModeTab>
            {previous && <ModeTab value="changes">{t("changes")}</ModeTab>}
            {decide && <ModeTab value="edit">{t("edit")}</ModeTab>}
          </Tabs.List>
          <Tabs.Panel value="preview" className={PANEL_CLASS}>
            <StageOutputView
              runId={run.id}
              outputId={output.id}
              narrowed={narrowed}
              literature={papersFrom}
            />
          </Tabs.Panel>
          {previous && (
            <Tabs.Panel value="changes" className={PANEL_CLASS}>
              <ChangesView
                previous={previous}
                previousNarrowed={view.previousNarrowed}
                narrowed={narrowed}
                output={output}
              />
            </Tabs.Panel>
          )}
          {decide && (
            <Tabs.Panel value="edit" className={PANEL_CLASS}>
              <EditOutput
                stage={stage}
                output={output}
                edit={edit}
                onEdit={(text) => setDraft({ baseSha: draft?.baseSha ?? output.sha256, text })}
                onReset={() => setDraft(null)}
                approval={approval}
              />
            </Tabs.Panel>
          )}
        </Tabs.Root>
        {decide && (
          <div className="grid gap-2">
            <Label htmlFor={`${ids}-comment`}>{t("comment")}</Label>
            <Textarea
              id={`${ids}-comment`}
              value={comment}
              onChange={(event) => approval.setComment(event.target.value)}
              maxLength={MAX_COMMENT_LENGTH}
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
        )}
      </CardContent>
      {decide && (
        <CardFooter className="flex flex-wrap items-center justify-end gap-2 border-t pt-4">
          {edit.changed && (
            <p className="mr-auto text-xs text-muted-foreground">{t("editsPending")}</p>
          )}
          <Button variant="destructive" disabled={locked} onClick={() => setConfirmReject(true)}>
            <ThumbsDownIcon aria-hidden />
            {sendingLabel("reject", t("reject"))}
          </Button>
          <Button variant="outline" disabled={locked} onClick={requestChanges}>
            <MessageSquareIcon aria-hidden />
            {sendingLabel("request_changes", t("requestChanges"))}
          </Button>
          <Button disabled={locked} onClick={approval.approve}>
            <ThumbsUpIcon aria-hidden />
            {sendingLabel("approve", t("approve"))}
          </Button>
        </CardFooter>
      )}

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
                approval.reject();
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

/**
 * Approve / request changes / reject the output waiting for review (useApprovalDecision), or
 * approve a corrected copy of it. The decision carries the output id and sha256 the reviewer
 * saw; if the output changed meanwhile, the API answers 409, and if a new version arrives while
 * the panel is open, the buttons stay locked until the reviewer acknowledges it. An edit that
 * fails the stage's schema (422) says which field.
 */
export function ApprovalPanel({
  run,
  literature,
}: {
  run: RunDetail;
  /** The literature the preview's citations refer to; default: the run's latest. */
  literature?: LiteratureOutput | null;
}) {
  return <ReviewCard run={run} literature={literature} decide />;
}

/** The output waiting for review, for people who may look but not decide. */
export function AwaitingPreview({
  run,
  literature,
}: {
  run: RunDetail;
  literature?: LiteratureOutput | null;
}) {
  return <ReviewCard run={run} literature={literature} decide={false} />;
}
