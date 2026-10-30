"use client";

import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { normalizeText } from "./diff-files";
import { type HighlightToken, highlightLanguage, highlightLines } from "./shiki";

type Highlighted = { code: string; language: string; lines: HighlightToken[][] };

/** Syntax tokens per line once the highlighter is ready; null while plain text is shown. */
function useHighlightedLines(code: string, language: string | null): HighlightToken[][] | null {
  const [highlighted, setHighlighted] = useState<Highlighted | null>(null);
  useEffect(() => {
    const lang = language ? highlightLanguage(language) : null;
    if (!lang) {
      return;
    }
    let cancelled = false;
    highlightLines(code, lang)
      .then((lines) => {
        if (!cancelled && lines) {
          setHighlighted({ code, language: lang, lines });
        }
      })
      .catch(() => {
        // Plain text stays on screen; highlighting is an enhancement.
      });
    return () => {
      cancelled = true;
    };
  }, [code, language]);
  return highlighted && highlighted.code === code && highlighted.language === language
    ? highlighted.lines
    : null;
}

export type CodeBlockProps = {
  code: string;
  /** A language name or alias (python, yaml, markdown, json, bash, toml); others stay plain. */
  language?: string | null;
  /** Accessible name of the scrollable code region. */
  label: string;
  /** Hide the line numbers. */
  hideLineNumbers?: boolean;
  /** CSS max-height of the scroll area, e.g. "32rem". */
  maxHeight?: string;
  className?: string;
};

/**
 * Highlighted, read-only code with line numbers that are not copied with the text. Plain text
 * shows at once (also on the server); colours arrive when the shared highlighter is ready.
 */
export function CodeBlock({
  code,
  language,
  label,
  hideLineNumbers = false,
  maxHeight,
  className,
}: CodeBlockProps) {
  const resolved = highlightLanguage(language ?? null);
  // A final newline ends the last line; it does not start an empty one.
  const text = useMemo(() => normalizeText(code).replace(/\n$/, ""), [code]);
  const highlighted = useHighlightedLines(text, resolved);
  const plain = useMemo(() => text.split("\n"), [text]);
  const lineCount = highlighted?.length ?? plain.length;
  const gutter = `${String(lineCount).length + 2}ch`;
  return (
    <section
      aria-label={label}
      data-slot="code-block"
      // biome-ignore lint/a11y/noNoninteractiveTabindex: keyboard users must be able to scroll it
      tabIndex={0}
      className={cn(
        "overflow-auto font-mono text-xs leading-5 outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset",
        className,
      )}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <pre className="w-max min-w-full py-2">
        <code className="grid">
          {Array.from({ length: lineCount }, (_, index) => (
            <span
              // Lines are positional: line N is always at index N - 1.
              // biome-ignore lint/suspicious/noArrayIndexKey: line numbers are the identity
              key={index}
              className="grid grid-cols-[auto_1fr] hover:bg-muted/50"
            >
              {hideLineNumbers ? (
                <span />
              ) : (
                <span
                  aria-hidden
                  className="pr-3 pl-2 text-right text-muted-foreground tabular-nums select-none"
                  style={{ minWidth: gutter }}
                >
                  {index + 1}
                </span>
              )}
              <span data-code className="pr-4 whitespace-pre">
                {highlighted
                  ? (highlighted[index] ?? []).map((token, position) => (
                      <span
                        // biome-ignore lint/suspicious/noArrayIndexKey: tokens are positional
                        key={position}
                        style={token.style as CSSProperties | undefined}
                      >
                        {token.content}
                      </span>
                    ))
                  : (plain[index] ?? "")}
                {"\n"}
              </span>
            </span>
          ))}
        </code>
      </pre>
    </section>
  );
}
