import { diffLines } from "diff";
import type { CodeFile } from "@/client";
import { normalizePath } from "./file-tree";

export type FileChangeStatus = "added" | "removed" | "modified" | "renamed" | "unchanged";

export type FileChange = {
  /** The file's path in the new version (the old path for a removed file). */
  path: string;
  /** For a rename: where the file was. */
  previousPath?: string;
  status: FileChangeStatus;
  before?: CodeFile;
  after?: CodeFile;
  /** Lines added and removed. */
  additions: number;
  deletions: number;
};

/** Line endings normalised, so a CRLF checkout does not count as a change. */
export function normalizeText(text: string): string {
  return text.replace(/\r\n?/g, "\n");
}

export function countLines(text: string): number {
  if (text.length === 0) {
    return 0;
  }
  return normalizeText(text).replace(/\n$/, "").split("\n").length;
}

/** Added and removed line counts between two texts (a missing final newline is ignored). */
export function lineChanges(
  before: string,
  after: string,
): { additions: number; deletions: number } {
  const ending = (text: string) => {
    const normalized = normalizeText(text);
    return normalized.length === 0 || normalized.endsWith("\n") ? normalized : `${normalized}\n`;
  };
  let additions = 0;
  let deletions = 0;
  for (const change of diffLines(ending(before), ending(after))) {
    if (change.added) {
      additions += change.count;
    } else if (change.removed) {
      deletions += change.count;
    }
  }
  return { additions, deletions };
}

const STATUS_ORDER: Record<FileChangeStatus, number> = {
  modified: 0,
  added: 1,
  renamed: 2,
  removed: 3,
  unchanged: 4,
};

const collator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

/**
 * Compares two versions of the generated files by path: added, removed, modified or
 * unchanged, with a removed and an added file of identical content reported as one rename.
 * Results are sorted by path.
 */
export function diffCodeFiles(
  before: readonly CodeFile[],
  after: readonly CodeFile[],
): FileChange[] {
  const oldFiles = new Map(before.map((file) => [normalizePath(file.path), file]));
  const newFiles = new Map(after.map((file) => [normalizePath(file.path), file]));
  const changes: FileChange[] = [];
  const added: FileChange[] = [];
  const removed: FileChange[] = [];

  for (const [path, file] of newFiles) {
    const old = oldFiles.get(path);
    if (!old) {
      added.push({
        path,
        status: "added",
        after: file,
        additions: countLines(file.content),
        deletions: 0,
      });
    } else if (normalizeText(old.content) === normalizeText(file.content)) {
      changes.push({
        path,
        status: "unchanged",
        before: old,
        after: file,
        additions: 0,
        deletions: 0,
      });
    } else {
      changes.push({
        path,
        status: "modified",
        before: old,
        after: file,
        ...lineChanges(old.content, file.content),
      });
    }
  }
  for (const [path, file] of oldFiles) {
    if (!newFiles.has(path)) {
      removed.push({
        path,
        status: "removed",
        before: file,
        additions: 0,
        deletions: countLines(file.content),
      });
    }
  }

  // A deleted file whose exact content reappears under a new path was moved.
  for (const gone of removed) {
    const content = normalizeText(gone.before?.content ?? "");
    const index = added.findIndex(
      (candidate) => normalizeText(candidate.after?.content ?? "") === content,
    );
    const moved = index === -1 ? undefined : added.splice(index, 1)[0];
    if (moved) {
      changes.push({
        path: moved.path,
        previousPath: gone.path,
        status: "renamed",
        before: gone.before,
        after: moved.after,
        additions: 0,
        deletions: 0,
      });
    } else {
      changes.push(gone);
    }
  }
  changes.push(...added);
  return changes.sort((a, b) => collator.compare(a.path, b.path));
}

/** Changed files first (modified, added, renamed, removed), then unchanged ones, by path. */
export function sortByStatus(changes: readonly FileChange[]): FileChange[] {
  return [...changes].sort(
    (a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || collator.compare(a.path, b.path),
  );
}
