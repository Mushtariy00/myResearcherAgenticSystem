"use client";

import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useId, useMemo, useRef, useState } from "react";
import type { CodeFile } from "@/client";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { diffCodeFiles, type FileChange, type FileChangeStatus, sortByStatus } from "./diff-files";
import { buildFileTree, normalizePath } from "./file-tree";
import { FileTreeView } from "./file-tree-view";
import { UnifiedDiff } from "./unified-diff";
import { useElementWidth } from "./use-dom";

const MonacoDiffEditor = dynamic(() => import("./monaco-diff-editor"), {
  ssr: false,
  loading: () => (
    <div className="grid gap-2 p-4">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  ),
});

/** Below this container width the side-by-side editor has no room; the unified view is used. */
const SPLIT_MIN_WIDTH = 768;

const STATUS_TONES: Record<FileChangeStatus, string | undefined> = {
  added: "success",
  removed: "danger",
  modified: "warning",
  renamed: "info",
  unchanged: undefined,
};

const STATUS_LETTERS: Record<FileChangeStatus, string> = {
  added: "A",
  removed: "D",
  modified: "M",
  renamed: "R",
  unchanged: "",
};

function ChangeMarker({ change }: { change: FileChange }) {
  const t = useTranslations("shared.diff");
  const tone = STATUS_TONES[change.status];
  return (
    <span className="flex shrink-0 items-center gap-1.5">
      {(change.additions > 0 || change.deletions > 0) && (
        <span className="font-sans text-[0.7rem] tabular-nums" aria-hidden>
          <span data-tone="success" className="text-(--tone-fg)">
            +{change.additions}
          </span>{" "}
          <span data-tone="danger" className="text-(--tone-fg)">
            −{change.deletions}
          </span>
        </span>
      )}
      {tone ? (
        <span
          data-tone={tone}
          title={t(`status.${change.status}`)}
          className="inline-flex size-4 items-center justify-center rounded-sm bg-(--tone)/20 font-sans text-[0.65rem] font-semibold text-(--tone-fg)"
        >
          <span aria-hidden>{STATUS_LETTERS[change.status]}</span>
        </span>
      ) : null}
      <span className="sr-only">
        {t(`status.${change.status}`)}
        {(change.additions > 0 || change.deletions > 0) &&
          `, ${t("lineCounts", { additions: change.additions, deletions: change.deletions })}`}
      </span>
    </span>
  );
}

export type CodeDiffProps = {
  /** The earlier version of the generated files. */
  before: readonly CodeFile[];
  /** The version under review. */
  after: readonly CodeFile[];
  /** Controlled selection (a path in the new version, or the old path of a deleted file). */
  selectedPath?: string;
  defaultPath?: string;
  onSelectPath?: (path: string) => void;
  /** "auto": side by side (Monaco) on wide containers, unified elsewhere and in tests. */
  view?: "auto" | "split" | "unified";
  /** CSS height of the diff area; default 32rem. */
  height?: string;
  className?: string;
};

/**
 * Two versions of the generated code: a file list marked added (A), deleted (D), changed (M) or
 * renamed (R) with line counts, and the selected file's diff, in Monaco's read-only diff editor
 * (loaded on demand) or a lightweight unified diff.
 */
export function CodeDiff({
  before,
  after,
  selectedPath,
  defaultPath,
  onSelectPath,
  view = "auto",
  height = "32rem",
  className,
}: CodeDiffProps) {
  const t = useTranslations("shared.diff");
  const container = useRef<HTMLDivElement>(null);
  const width = useElementWidth(container);
  const switchId = useId();
  const [showUnchanged, setShowUnchanged] = useState(false);
  const [preferSplit, setPreferSplit] = useState(true);
  const [ownSelection, setOwnSelection] = useState(
    defaultPath ? normalizePath(defaultPath) : undefined,
  );

  const changes = useMemo(() => diffCodeFiles(before, after), [before, after]);
  const changed = useMemo(
    () => changes.filter((change) => change.status !== "unchanged"),
    [changes],
  );
  const listed = showUnchanged ? changes : changed;
  const byPath = useMemo(() => new Map(changes.map((change) => [change.path, change])), [changes]);
  const tree = useMemo(() => buildFileTree(listed.map((change) => change.path)), [listed]);

  const wanted = selectedPath !== undefined ? normalizePath(selectedPath) : ownSelection;
  const chosen = wanted ? byPath.get(wanted) : undefined;
  const current =
    chosen && (showUnchanged || chosen.status !== "unchanged") ? chosen : sortByStatus(listed)[0];

  const canSplit = width !== undefined && width >= SPLIT_MIN_WIDTH;
  const split = view === "split" ? canSplit : view === "auto" && canSplit && preferSplit;

  function select(path: string) {
    setOwnSelection(path);
    onSelectPath?.(path);
  }

  if (changes.length === 0) {
    return (
      <div
        data-slot="code-diff"
        className={cn(
          "rounded-xl border border-dashed px-6 py-10 text-center text-sm text-muted-foreground",
          className,
        )}
      >
        {t("empty")}
      </div>
    );
  }

  return (
    <div
      ref={container}
      data-slot="code-diff"
      className={cn("@container overflow-hidden rounded-xl border bg-card", className)}
    >
      <div className="grid @3xl:grid-cols-[minmax(10rem,16rem)_minmax(0,1fr)]">
        <nav
          aria-label={t("files")}
          className="grid max-h-56 content-start gap-2 overflow-auto border-b p-2 @3xl:max-h-none @3xl:border-r @3xl:border-b-0"
        >
          <p className="px-1.5 text-xs text-muted-foreground" aria-live="polite">
            {t("summary", { count: changed.length })}
          </p>
          {listed.length > 0 && (
            <FileTreeView
              nodes={tree}
              selectedPath={current?.path}
              onSelect={select}
              renderMarker={(path) => {
                const change = byPath.get(path);
                return change ? <ChangeMarker change={change} /> : null;
              }}
              fileClassName={(path) =>
                byPath.get(path)?.status === "removed" ? "line-through decoration-1" : undefined
              }
            />
          )}
          {changes.length > changed.length && (
            <label
              htmlFor={switchId}
              className="flex items-center gap-2 px-1.5 pt-1 text-xs text-muted-foreground"
            >
              <Switch id={switchId} checked={showUnchanged} onCheckedChange={setShowUnchanged} />
              {t("showUnchanged")}
            </label>
          )}
        </nav>
        <div className="grid min-w-0 content-start">
          {current ? (
            <>
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 border-b px-3 py-2">
                <span
                  className="min-w-0 truncate font-mono text-xs font-medium"
                  title={current.path}
                >
                  {current.path}
                </span>
                {current.previousPath && (
                  <span className="text-xs text-muted-foreground">
                    {t("renamedFrom", { path: current.previousPath })}
                  </span>
                )}
                <span
                  data-tone={STATUS_TONES[current.status] ?? "neutral"}
                  className="inline-flex h-5 items-center rounded-full bg-(--tone)/15 px-2 text-xs font-medium text-(--tone-fg)"
                >
                  {t(`status.${current.status}`)}
                </span>
                {view === "auto" && canSplit && (
                  <fieldset className="ml-auto flex items-center rounded-lg border p-0.5 text-xs">
                    <legend className="sr-only">{t("view")}</legend>
                    {(["split", "unified"] as const).map((option) => (
                      <button
                        key={option}
                        type="button"
                        aria-pressed={(option === "split") === preferSplit}
                        onClick={() => setPreferSplit(option === "split")}
                        className="rounded-md px-2 py-0.5 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:bg-muted aria-pressed:font-medium"
                      >
                        {t(option)}
                      </button>
                    ))}
                  </fieldset>
                )}
              </div>
              {current.status === "unchanged" || current.status === "renamed" ? (
                <p className="p-4 text-sm text-muted-foreground">{t("noChanges")}</p>
              ) : split ? (
                <MonacoDiffEditor
                  original={current.before?.content ?? ""}
                  modified={current.after?.content ?? ""}
                  language={(current.after ?? current.before)?.language}
                  path={current.path}
                  label={t("changesIn", { path: current.path })}
                  height={height}
                />
              ) : (
                <UnifiedDiff
                  before={current.before?.content ?? ""}
                  after={current.after?.content ?? ""}
                  label={t("changesIn", { path: current.path })}
                  maxHeight={height}
                />
              )}
            </>
          ) : (
            <p className="p-4 text-sm text-muted-foreground">{t("identical")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
