"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import type { CodeFile } from "@/client";
import { cn } from "@/lib/utils";
import { CodeBlock } from "./code-block";
import { CopyButton } from "./copy-button";
import { countLines } from "./diff-files";
import { DownloadLink } from "./download-link";
import { buildFileTree, flattenFiles, normalizePath } from "./file-tree";
import { FileTreeView } from "./file-tree-view";

export type CodeViewerProps = {
  files: readonly CodeFile[];
  /** Controlled selection (a file path). */
  selectedPath?: string;
  /** First file shown when uncontrolled, e.g. the coding output's entrypoint. */
  defaultPath?: string;
  onSelectPath?: (path: string) => void;
  /** Same-origin attachment URL with every file (e.g. the code archive artifact). */
  downloadUrl?: string;
  downloadFilename?: string;
  /** CSS max-height of the code area; default 36rem. */
  maxHeight?: string;
  className?: string;
};

/**
 * Generated code: a file tree built from the CodeFile paths and the selected file with syntax
 * highlighting, line numbers, its role, a copy button and an optional archive download. The tree
 * sits beside the code on wide containers and above it on narrow ones.
 */
export function CodeViewer({
  files,
  selectedPath,
  defaultPath,
  onSelectPath,
  downloadUrl,
  downloadFilename,
  maxHeight = "36rem",
  className,
}: CodeViewerProps) {
  const t = useTranslations("shared.code");
  const byPath = useMemo(
    () => new Map(files.map((file) => [normalizePath(file.path), file])),
    [files],
  );
  const tree = useMemo(() => buildFileTree([...byPath.keys()]), [byPath]);
  const ordered = useMemo(() => flattenFiles(tree), [tree]);
  const [ownSelection, setOwnSelection] = useState<string | undefined>(
    defaultPath ? normalizePath(defaultPath) : undefined,
  );

  const wanted = selectedPath !== undefined ? normalizePath(selectedPath) : ownSelection;
  const currentPath = wanted && byPath.has(wanted) ? wanted : ordered[0];
  const current = currentPath ? byPath.get(currentPath) : undefined;

  function select(path: string) {
    setOwnSelection(path);
    onSelectPath?.(path);
  }

  if (files.length === 0) {
    return (
      <div
        data-slot="code-viewer"
        className={cn(
          "rounded-xl border border-dashed px-6 py-10 text-center text-sm text-muted-foreground",
          className,
        )}
      >
        {t("empty")}
      </div>
    );
  }

  const lineCount = current ? countLines(current.content) : 0;
  return (
    <div
      data-slot="code-viewer"
      className={cn("@container overflow-hidden rounded-xl border bg-card", className)}
    >
      <div className="grid @3xl:grid-cols-[minmax(10rem,15rem)_minmax(0,1fr)]">
        <nav
          aria-label={t("files")}
          className="max-h-48 overflow-auto border-b p-2 @3xl:max-h-none @3xl:border-r @3xl:border-b-0"
        >
          <FileTreeView nodes={tree} selectedPath={currentPath} onSelect={select} />
        </nav>
        <div className="grid min-w-0 grid-rows-[auto_minmax(0,1fr)]">
          {current && currentPath ? (
            <>
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 border-b px-3 py-2">
                <span
                  className="min-w-0 truncate font-mono text-xs font-medium"
                  title={currentPath}
                >
                  {currentPath}
                </span>
                <span className="inline-flex h-5 items-center rounded-full border px-2 text-xs text-muted-foreground">
                  {t(`roles.${current.role}`)}
                </span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {t("lines", { count: lineCount })}
                </span>
                <span className="ml-auto flex items-center gap-1">
                  <CopyButton value={current.content} label={t("copy", { path: currentPath })} />
                  {downloadUrl && (
                    <DownloadLink href={downloadUrl} filename={downloadFilename} variant="ghost">
                      {t("downloadAll")}
                    </DownloadLink>
                  )}
                </span>
              </div>
              <CodeBlock
                code={current.content}
                language={current.language || currentPath.split(".").pop()}
                label={t("contents", { path: currentPath })}
                maxHeight={maxHeight}
              />
            </>
          ) : (
            <p className="p-6 text-sm text-muted-foreground">{t("noFileSelected")}</p>
          )}
        </div>
      </div>
    </div>
  );
}
