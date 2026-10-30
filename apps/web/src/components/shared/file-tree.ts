export type FileTreeNode =
  | { kind: "folder"; name: string; path: string; children: FileTreeNode[] }
  | { kind: "file"; name: string; path: string };

/** `a\b` and `./a/b` both become `a/b`; empty segments are dropped. */
export function normalizePath(path: string): string {
  return path
    .replace(/\\/g, "/")
    .split("/")
    .filter((segment) => segment.length > 0 && segment !== ".")
    .join("/");
}

const collator = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

function sortNodes(nodes: FileTreeNode[]): FileTreeNode[] {
  nodes.sort((a, b) =>
    a.kind === b.kind ? collator.compare(a.name, b.name) : a.kind === "folder" ? -1 : 1,
  );
  for (const node of nodes) {
    if (node.kind === "folder") {
      sortNodes(node.children);
    }
  }
  return nodes;
}

/**
 * A folder tree from file paths: folders first, then files, each in natural order. A path that
 * names both a file and a folder keeps both (the file under its own name).
 */
export function buildFileTree(paths: readonly string[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];
  const folders = new Map<string, FileTreeNode[]>();
  for (const raw of paths) {
    const path = normalizePath(raw);
    if (!path) {
      continue;
    }
    const segments = path.split("/");
    let siblings = root;
    let prefix = "";
    for (const [index, name] of segments.entries()) {
      prefix = prefix ? `${prefix}/${name}` : name;
      if (index === segments.length - 1) {
        if (!siblings.some((node) => node.kind === "file" && node.path === prefix)) {
          siblings.push({ kind: "file", name, path: prefix });
        }
        break;
      }
      let children = folders.get(prefix);
      if (!children) {
        children = [];
        folders.set(prefix, children);
        siblings.push({ kind: "folder", name, path: prefix, children });
      }
      siblings = children;
    }
  }
  return sortNodes(root);
}

/** File paths in tree order (what a reader sees top to bottom). */
export function flattenFiles(nodes: readonly FileTreeNode[]): string[] {
  return nodes.flatMap((node) =>
    node.kind === "file" ? [node.path] : flattenFiles(node.children),
  );
}
