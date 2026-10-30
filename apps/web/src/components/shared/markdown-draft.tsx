"use client";

import "katex/dist/katex.min.css";
import { HashIcon, TableOfContentsIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  type ComponentPropsWithoutRef,
  createContext,
  type ReactNode,
  useContext,
  useId,
  useMemo,
  useState,
} from "react";
import Markdown, { type Components, type ExtraProps } from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { Citation } from "@/client";
import { cn } from "@/lib/utils";
import { authorNames } from "./format";
import { DRAFT_SANITIZE_SCHEMA, type DraftHeading, rehypeDraft } from "./markdown-plugins";
import { indexPapers, type PaperSummary } from "./paper-summary";
import { Tooltip, TooltipContent } from "./tooltip";
import { isSameOriginPath } from "./urls";

type CitePayload = { key: number };

type DraftContextValue = {
  paperFor: (key: number) => PaperSummary | undefined;
  onCite?: (key: number, paper: PaperSummary | undefined) => void;
  tooltip: Tooltip.Handle<CitePayload>;
  headingText: (id: string) => string | undefined;
};

const DraftContext = createContext<DraftContextValue | null>(null);

function useDraft(): DraftContextValue {
  const value = useContext(DraftContext);
  if (!value) {
    throw new Error("MarkdownDraft components rendered outside MarkdownDraft");
  }
  return value;
}

function CitationButton({ value }: { value: string }) {
  const t = useTranslations("shared.draft");
  const { paperFor, onCite, tooltip } = useDraft();
  const key = Number(value);
  const paper = paperFor(key);
  return (
    <Tooltip.Trigger
      handle={tooltip}
      payload={{ key }}
      data-slot="citation"
      data-cite={key}
      data-unresolved={paper ? undefined : true}
      aria-label={
        paper ? t("citation", { key, title: paper.title }) : t("citationUnknown", { key })
      }
      onClick={() => onCite?.(key, paper)}
      className={cn(
        "relative mx-px rounded-sm px-0.5 font-medium text-primary tabular-nums underline decoration-dotted underline-offset-2 outline-none after:absolute after:-inset-1 hover:decoration-solid focus-visible:ring-3 focus-visible:ring-ring/50",
        !paper && "text-muted-foreground decoration-wavy",
      )}
    >
      {value}
    </Tooltip.Trigger>
  );
}

function CitationTooltip() {
  const t = useTranslations("shared.draft");
  const tPapers = useTranslations("shared.papers");
  const { paperFor, tooltip } = useDraft();
  return (
    <Tooltip.Root handle={tooltip}>
      {({ payload }) => {
        const paper = payload ? paperFor(payload.key) : undefined;
        if (!payload) {
          return null;
        }
        const authors = paper ? authorNames(paper.authors, 2) : null;
        return (
          <TooltipContent>
            {paper ? (
              <span className="grid gap-0.5">
                <span className="font-medium">{paper.title}</span>
                <span className="text-muted-foreground">
                  {t("authorsYear", {
                    authors: authors?.names
                      ? authors.truncated
                        ? tPapers("etAl", { names: authors.names })
                        : authors.names
                      : tPapers("unknownAuthors"),
                    year: paper.year,
                  })}
                </span>
              </span>
            ) : (
              t("notInReferences")
            )}
          </TooltipContent>
        );
      }}
    </Tooltip.Root>
  );
}

const HEADING_CLASSES = {
  1: "mt-8 mb-4 text-2xl font-semibold tracking-tight first:mt-0",
  2: "mt-8 mb-3 border-b pb-1 text-xl font-semibold tracking-tight",
  3: "mt-6 mb-2 text-lg font-semibold",
  4: "mt-5 mb-2 font-semibold",
  5: "mt-4 mb-2 font-semibold",
  6: "mt-4 mb-2 font-semibold text-muted-foreground",
} as const;

type HeadingProps = ComponentPropsWithoutRef<"h1"> & ExtraProps;

/** A heading with its generated id and a "#" link to it (visible on hover and focus). */
function DraftHeadingElement({
  level,
  id,
  className,
  children,
}: {
  level: keyof typeof HEADING_CLASSES;
  id?: string;
  className?: string;
  children?: ReactNode;
}) {
  const t = useTranslations("shared.draft");
  const { headingText } = useDraft();
  const Tag = `h${level}` as const;
  // GFM's visually hidden "Footnotes" label keeps its class and gets no anchor.
  const hidden = className?.split(" ").includes("sr-only") ?? false;
  return (
    <Tag
      id={id}
      className={cn(
        hidden ? "sr-only" : "group scroll-mt-24 break-words",
        !hidden && HEADING_CLASSES[level],
      )}
    >
      {children}
      {id && !hidden && (
        <a
          href={`#${id}`}
          aria-label={t("headingLink", { title: headingText(id) ?? "" })}
          className="ml-2 inline-flex align-middle text-muted-foreground opacity-0 outline-none group-hover:opacity-100 focus-visible:opacity-100 focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <HashIcon aria-hidden className="size-4" />
        </a>
      )}
    </Tag>
  );
}

/** Same-origin images only: drafts never make the reader's browser call another server. */
function DraftImage({ src, alt }: ComponentPropsWithoutRef<"img">) {
  const t = useTranslations("shared.draft");
  if (typeof src === "string" && isSameOriginPath(src)) {
    // biome-ignore lint/performance/noImgElement: arbitrary same-origin attachments, unknown sizes
    return <img src={src} alt={alt ?? ""} loading="lazy" className="my-4 max-w-full rounded-lg" />;
  }
  return (
    <span className="inline-block rounded-md border border-dashed px-2 py-1 text-xs text-muted-foreground">
      {alt ? t("imageBlocked", { alt }) : t("imageBlockedUntitled")}
    </span>
  );
}

/**
 * Links keep their sanitised attributes (footnote ids, aria-describedby, data-footnote-*).
 * External links open in a new tab without referrer; a link the URL filter emptied
 * (javascript:, data: and the like) is plain text.
 */
function DraftLink({
  node: _node,
  href,
  children,
  className,
  ...rest
}: ComponentPropsWithoutRef<"a"> & ExtraProps) {
  if (!href) {
    return <span>{children}</span>;
  }
  const external = !href.startsWith("#") && !isSameOriginPath(href);
  return (
    <a
      {...rest}
      href={href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer nofollow ugc" } : {})}
      className={cn(
        "font-medium text-primary underline underline-offset-4 hover:decoration-2",
        className,
      )}
    >
      {children}
    </a>
  );
}

function heading(level: keyof typeof HEADING_CLASSES, { id, className, children }: HeadingProps) {
  return (
    <DraftHeadingElement level={level} id={id} className={className}>
      {children}
    </DraftHeadingElement>
  );
}

const COMPONENTS: Components = {
  h1: (props) => heading(1, props),
  h2: (props) => heading(2, props),
  h3: (props) => heading(3, props),
  h4: (props) => heading(4, props),
  h5: (props) => heading(5, props),
  h6: (props) => heading(6, props),
  p: ({ children }) => <p className="my-3 leading-7">{children}</p>,
  a: (props) => <DraftLink {...props} />,
  img: ({ src, alt }) => <DraftImage src={src} alt={alt} />,
  ul: ({ children, className }) => (
    <ul className={cn("my-3 ml-6 list-disc [&>li]:mt-1", className)}>{children}</ul>
  ),
  ol: ({ children, start }) => (
    <ol start={start} className="my-3 ml-6 list-decimal [&>li]:mt-1">
      {children}
    </ol>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-4 border-l-2 pl-4 text-muted-foreground">{children}</blockquote>
  ),
  pre: ({ children }) => (
    <pre className="my-4 overflow-x-auto rounded-lg border bg-muted/40 p-3 font-mono text-xs leading-5 [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  code: ({ children, className }) => (
    <code className={cn("rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]", className)}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="my-4 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children, style }) => (
    <th className="border-b px-2 py-1 text-left font-medium" style={style}>
      {children}
    </th>
  ),
  td: ({ children, style }) => (
    <td className="border-b px-2 py-1 align-top" style={style}>
      {children}
    </td>
  ),
  hr: () => <hr className="my-6" />,
  button: (props) => {
    const cite = (props as { "data-cite"?: unknown })["data-cite"];
    return typeof cite === "string" ? (
      <CitationButton value={cite} />
    ) : (
      <span>{props.children}</span>
    );
  },
};

/** Headings for the contents: the main level (skipping a lone title) and the one below it. */
export function tocEntries(headings: readonly DraftHeading[]): DraftHeading[] {
  if (headings.length === 0) {
    return [];
  }
  let base = Math.min(...headings.map((heading) => heading.depth));
  if (
    headings.filter((heading) => heading.depth === base).length === 1 &&
    headings.some((heading) => heading.depth > base)
  ) {
    base += 1;
  }
  return headings.filter((heading) => heading.depth >= base && heading.depth <= base + 1);
}

function TableOfContents({ headings }: { headings: readonly DraftHeading[] }) {
  const t = useTranslations("shared.draft");
  const listId = useId();
  const [open, setOpen] = useState(false);
  const base = Math.min(...headings.map((heading) => heading.depth));
  return (
    <nav
      aria-label={t("toc")}
      className="text-sm @4xl:sticky @4xl:top-4 @4xl:max-h-[calc(100dvh-2rem)] @4xl:overflow-auto"
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 rounded-md px-1 py-0.5 text-xs font-medium text-muted-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50 @4xl:hidden"
      >
        <TableOfContentsIcon aria-hidden className="size-3.5" />
        {t("toc")}
      </button>
      <p className="hidden px-1 text-xs font-medium text-muted-foreground @4xl:block">{t("toc")}</p>
      <ol id={listId} className={cn("mt-2 grid gap-1 @4xl:grid", open ? "grid" : "hidden")}>
        {headings.map((heading) => (
          <li
            key={heading.id}
            style={{ paddingInlineStart: `${(heading.depth - base) * 0.75}rem` }}
          >
            <a
              href={`#${heading.id}`}
              className="block rounded-sm px-1 py-0.5 text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {heading.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

export type MarkdownDraftProps = {
  /** The draft (e.g. `WritingOutput.markdown`). Raw HTML in it is never rendered. */
  markdown: string;
  /** Citation keys of the draft (`WritingOutput.citations`): `[n]` → paper id. */
  citations?: readonly Citation[];
  /** Papers the citations point to, for titles in the tooltips. */
  papers?: readonly PaperSummary[];
  /** Called when a `[n]` marker is pressed (the paper is undefined for unknown keys). */
  onCite?: (key: number, paper: PaperSummary | undefined) => void;
  /** Show a table of contents when the draft has at least two sections (default true). */
  toc?: boolean;
  /** Prefix of heading ids, unique per page when showing two drafts (default "section-"). */
  idPrefix?: string;
  className?: string;
};

/**
 * A research draft from Markdown: GFM tables and footnotes, KaTeX math, heading anchors and a
 * table of contents. `[n]` citation markers become buttons with the cited paper's title in a
 * tooltip. Output is sanitised (rehype-sanitize) and raw HTML is never rendered.
 */
export function MarkdownDraft({
  markdown,
  citations,
  papers,
  onCite,
  toc = true,
  idPrefix = "section-",
  className,
}: MarkdownDraftProps) {
  const [tooltip] = useState(() => Tooltip.createHandle<CitePayload>());
  const byId = useMemo(() => indexPapers(papers), [papers]);
  const keyToPaper = useMemo(
    () => new Map((citations ?? []).map((citation) => [citation.key, citation.paper_id])),
    [citations],
  );

  const rendered = useMemo(() => {
    const headings: DraftHeading[] = [];
    const element = Markdown({
      children: markdown,
      remarkPlugins: [remarkGfm, remarkMath],
      remarkRehypeOptions: { clobberPrefix: "" },
      rehypePlugins: [
        [rehypeSanitize, DRAFT_SANITIZE_SCHEMA],
        [rehypeDraft, { idPrefix, headings }],
        [rehypeKatex, { trust: false, strict: "ignore", errorColor: "var(--destructive)" }],
      ],
      skipHtml: true,
      components: COMPONENTS,
    });
    return { element, headings };
  }, [markdown, idPrefix]);

  const context = useMemo<DraftContextValue>(() => {
    const titles = new Map(rendered.headings.map((heading) => [heading.id, heading.text]));
    return {
      paperFor: (key) => {
        const paperId = keyToPaper.get(key);
        return paperId ? byId.get(paperId) : undefined;
      },
      onCite,
      tooltip,
      headingText: (id) => titles.get(id),
    };
  }, [rendered.headings, keyToPaper, byId, onCite, tooltip]);

  const entries = toc ? tocEntries(rendered.headings) : [];
  return (
    <DraftContext.Provider value={context}>
      <div
        data-slot="markdown-draft"
        className={cn(
          "@container grid gap-6",
          entries.length >= 2 && "@4xl:grid-cols-[minmax(0,1fr)_14rem]",
          className,
        )}
      >
        {entries.length >= 2 && (
          <div className="@4xl:order-last">
            <TableOfContents headings={entries} />
          </div>
        )}
        <article className="min-w-0 text-sm break-words [&_.footnotes]:mt-8 [&_.footnotes]:border-t [&_.footnotes]:pt-4 [&_.footnotes]:text-xs [&_.katex-display]:overflow-x-auto [&_.katex-display]:overflow-y-hidden [&_.katex-display]:py-1">
          {rendered.element}
        </article>
      </div>
      <CitationTooltip />
    </DraftContext.Provider>
  );
}
