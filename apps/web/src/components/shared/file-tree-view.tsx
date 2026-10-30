"use client";

import { ChevronRightIcon, FileIcon, FolderIcon, FolderOpenIcon } from "lucide-react";
import { type ReactNode, useState } from "react";
import { cn } from "@/lib/utils";
import type { FileTreeNode } from "./file-tree";

export type FileTreeViewProps = {
  nodes: readonly FileTreeNode[];
  selectedPath?: string;
  onSelect: (path: string) => void;
  /** Extra content after a file name, e.g. a change marker. */
  renderMarker?: (path: string) => ReactNode;
  /** Classes for a file button, e.g. strike-through for deleted files. */
  fileClassName?: (path: string) => string | undefined;
  className?: string;
};

/**
 * Nested folder lists of file buttons. Folders are disclosure buttons (aria-expanded) and start
 * open; the current file is marked with aria-current.
 */
export function FileTreeView({
  nodes,
  selectedPath,
  onSelect,
  renderMarker,
  fileClassName,
  className,
}: FileTreeViewProps) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());

  function toggle(path: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (!next.delete(path)) {
        next.add(path);
      }
      return next;
    });
  }

  function renderNodes(list: readonly FileTreeNode[], depth: number): ReactNode {
    return (
      <ul className={cn("grid gap-px", depth > 0 && "ml-3 border-l pl-1.5")}>
        {list.map((node) => {
          if (node.kind === "folder") {
            const open = !collapsed.has(node.path);
            const Icon = open ? FolderOpenIcon : FolderIcon;
            return (
              <li key={`d:${node.path}`}>
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => toggle(node.path)}
                  className="flex w-full min-w-0 items-center gap-1 rounded-md px-1.5 py-1 text-left text-xs text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <ChevronRightIcon
                    aria-hidden
                    className={cn(
                      "size-3 shrink-0 transition-transform motion-reduce:transition-none",
                      open && "rotate-90",
                    )}
                  />
                  <Icon aria-hidden className="size-3.5 shrink-0" />
                  <span className="truncate">{node.name}</span>
                </button>
                {open && renderNodes(node.children, depth + 1)}
              </li>
            );
          }
          const current = node.path === selectedPath;
          return (
            <li key={`f:${node.path}`}>
              <button
                type="button"
                aria-current={current ? "true" : undefined}
                title={node.path}
                onClick={() => onSelect(node.path)}
                className={cn(
                  "flex w-full min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-left font-mono text-xs outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-[current=true]:bg-accent aria-[current=true]:font-medium aria-[current=true]:text-accent-foreground",
                  fileClassName?.(node.path),
                )}
              >
                <FileIcon aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">{node.name}</span>
                {renderMarker?.(node.path)}
              </button>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div data-slot="file-tree" className={className}>
      {renderNodes(nodes, 0)}
    </div>
  );
}
