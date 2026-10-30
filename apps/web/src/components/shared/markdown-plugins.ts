import { defaultSchema, type Options as SanitizeSchema } from "rehype-sanitize";

/**
 * Plugins and schema for MarkdownDraft. The pipeline is: markdown → GFM and math → HTML tree →
 * rehype-sanitize (GitHub's default schema, extended only to keep the math markers KaTeX reads)
 * → `rehypeDraft` (ours: heading ids, citations, footnote links) → rehype-katex. Raw HTML never
 * reaches the page, and KaTeX renders only after sanitising, from the math text alone.
 */

/** Default schema plus the `math-inline` / `math-display` classes rehype-katex looks for. */
export const DRAFT_SANITIZE_SCHEMA: SanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", /^language-./, "math-inline", "math-display"]],
  },
};

type HastText = { type: "text"; value: string };
type HastElement = {
  type: "element";
  tagName: string;
  properties: Record<string, unknown>;
  children: HastNode[];
};
type HastParent = { type: "root" | "element"; children: HastNode[] };
type HastNode = HastText | HastElement | { type: "root" | "comment" | "doctype" | "raw" };

export type DraftHeading = { id: string; depth: number; text: string };

export type DraftPluginOptions = {
  /** Prefix for generated heading ids (keeps them clear of other ids on the page). */
  idPrefix: string;
  /** Filled with the document's headings, in order (for the table of contents). */
  headings: DraftHeading[];
};

const HEADINGS = new Set(["h1", "h2", "h3", "h4", "h5", "h6"]);
/** Text in these elements is never turned into citation buttons. */
const NO_CITATIONS = new Set(["a", "button", "code", "pre", "kbd", "samp", "script", "style"]);
/** `[3]`, `[1, 4]`, `[2-5]`, `[2–5]`: groups of positive citation keys. */
const CITATION = /\[(\d{1,4}(?:\s*(?:,|–|—|-)\s*\d{1,4})*)\]/g;

function isElement(node: HastNode | HastParent): node is HastElement {
  return node.type === "element";
}

function hasChildren(node: HastNode | HastParent): node is HastParent {
  return "children" in node && Array.isArray(node.children);
}

export function hastText(node: HastNode | HastParent): string {
  if (node.type === "text") {
    return (node as HastText).value;
  }
  return hasChildren(node) ? node.children.map(hastText).join("") : "";
}

/** Lower-case, letters and digits of any script joined by hyphens ("2. Related Work" → "2-related-work"). */
export function slugify(text: string): string {
  return text
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
}

/** Splits `[n]` groups in a text into text and citation-button nodes; null if there are none. */
export function splitCitations(value: string): HastNode[] | null {
  const parts: HastNode[] = [];
  let last = 0;
  for (const match of value.matchAll(CITATION)) {
    const inner = match[1] ?? "";
    const tokens = inner.split(/(\s*(?:,|–|—|-)\s*)/);
    const keys = tokens.filter((_, index) => index % 2 === 0).map(Number);
    if (keys.some((key) => !Number.isInteger(key) || key < 1)) {
      continue; // "[0, 1]" is an interval, not a citation
    }
    const start = match.index ?? 0;
    if (start > last) {
      parts.push({ type: "text", value: value.slice(last, start) });
    }
    parts.push({ type: "text", value: "[" });
    tokens.forEach((token, index) => {
      if (index % 2 === 1) {
        parts.push({ type: "text", value: token });
        return;
      }
      parts.push({
        type: "element",
        tagName: "button",
        properties: { type: "button", dataCite: token },
        children: [{ type: "text", value: token }],
      });
    });
    parts.push({ type: "text", value: "]" });
    last = start + match[0].length;
  }
  if (parts.length === 0) {
    return null;
  }
  if (last < value.length) {
    parts.push({ type: "text", value: value.slice(last) });
  }
  return parts;
}

function classNames(element: HastElement): string[] {
  const value = element.properties.className;
  return Array.isArray(value)
    ? value.map(String)
    : typeof value === "string"
      ? value.split(" ")
      : [];
}

/** The rehype plugin: runs after sanitising, so the elements it adds are trusted markup. */
export function rehypeDraft({ idPrefix, headings }: DraftPluginOptions) {
  return (tree: HastParent) => {
    headings.length = 0;
    const ids = new Set<string>();
    const links: HastElement[] = [];
    const used = new Map<string, number>();

    const visit = (node: HastNode | HastParent, citationsAllowed: boolean) => {
      if (!hasChildren(node)) {
        return;
      }
      const element = isElement(node) ? node : undefined;
      if (element) {
        const existing = element.properties.id;
        if (typeof existing === "string") {
          ids.add(existing);
        }
        if (element.tagName === "a" && typeof element.properties.href === "string") {
          links.push(element);
        }
        if (HEADINGS.has(element.tagName) && typeof existing !== "string") {
          const text = hastText(element).trim();
          const base = `${idPrefix}${slugify(text) || "section"}`;
          const count = used.get(base) ?? 0;
          used.set(base, count + 1);
          const id = count === 0 ? base : `${base}-${count}`;
          element.properties.id = id;
          ids.add(id);
          if (!classNames(element).includes("sr-only")) {
            headings.push({ id, depth: Number(element.tagName.slice(1)), text });
          }
        }
      }
      const allowed = citationsAllowed && !(element && NO_CITATIONS.has(element.tagName));
      const children: HastNode[] = [];
      for (const child of node.children) {
        if (allowed && child.type === "text") {
          const split = splitCitations((child as HastText).value);
          if (split) {
            children.push(...split);
            continue;
          }
        }
        visit(child, allowed);
        children.push(child);
      }
      node.children = children;
    };
    visit(tree, true);

    // rehype-sanitize prefixes ids ("user-content-"); in-page links follow them.
    for (const link of links) {
      const href = link.properties.href as string;
      if (
        href.startsWith("#") &&
        !ids.has(href.slice(1)) &&
        ids.has(`user-content-${href.slice(1)}`)
      ) {
        link.properties.href = `#user-content-${href.slice(1)}`;
      }
    }
  };
}
