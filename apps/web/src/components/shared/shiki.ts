import type { HighlighterCore } from "shiki/core";

/**
 * One Shiki highlighter for the whole app, created on first use: the JavaScript regex engine
 * (no WebAssembly), GitHub light and dark themes, and only the languages generated code uses.
 * Tokens carry both themes as CSS variables (`--shiki-light`, `--shiki-dark`), and shared.css
 * picks one, so switching the theme never re-highlights.
 */

export type HighlightLanguage = "python" | "yaml" | "markdown" | "json" | "bash" | "toml";

const ALIASES: Record<string, HighlightLanguage> = {
  python: "python",
  py: "python",
  yaml: "yaml",
  yml: "yaml",
  markdown: "markdown",
  md: "markdown",
  json: "json",
  jsonc: "json",
  bash: "bash",
  sh: "bash",
  shell: "bash",
  shellscript: "bash",
  zsh: "bash",
  toml: "toml",
};

/** The highlight language for a file's declared language, else its extension; null = plain. */
export function highlightLanguage(
  language: string | null | undefined,
  path?: string,
): HighlightLanguage | null {
  const declared = language?.trim().toLowerCase();
  if (declared && ALIASES[declared]) {
    return ALIASES[declared];
  }
  const extension = path?.split(".").pop()?.toLowerCase();
  return (extension && ALIASES[extension]) || null;
}

/** Larger inputs are shown as plain text: highlighting them would block the main thread. */
export const MAX_HIGHLIGHT_CHARS = 200_000;
export const MAX_HIGHLIGHT_LINES = 5_000;

let highlighter: Promise<HighlighterCore> | undefined;

export function loadHighlighter(): Promise<HighlighterCore> {
  highlighter ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }] = await Promise.all([
      import("shiki/core"),
      import("shiki/engine/javascript"),
    ]);
    return createHighlighterCore({
      engine: createJavaScriptRegexEngine(),
      themes: [import("shiki/themes/github-light.mjs"), import("shiki/themes/github-dark.mjs")],
      langs: [
        import("shiki/langs/python.mjs"),
        import("shiki/langs/yaml.mjs"),
        import("shiki/langs/markdown.mjs"),
        import("shiki/langs/json.mjs"),
        import("shiki/langs/bash.mjs"),
        import("shiki/langs/toml.mjs"),
      ],
    });
  })().catch((error: unknown) => {
    highlighter = undefined; // a failed chunk load may succeed later
    throw error;
  });
  return highlighter;
}

export type HighlightToken = { content: string; style?: Record<string, string> };

/** Tokens per line, or null when the input is too large to highlight. */
export async function highlightLines(
  code: string,
  language: HighlightLanguage,
): Promise<HighlightToken[][] | null> {
  if (code.length > MAX_HIGHLIGHT_CHARS) {
    return null;
  }
  let lineCount = 1;
  for (let index = code.indexOf("\n"); index !== -1; index = code.indexOf("\n", index + 1)) {
    lineCount += 1;
    if (lineCount > MAX_HIGHLIGHT_LINES) {
      return null;
    }
  }
  const shiki = await loadHighlighter();
  const { tokens } = shiki.codeToTokens(code, {
    lang: language,
    themes: { light: "github-light", dark: "github-dark" },
    defaultColor: false,
    tokenizeMaxLineLength: 2_000,
  });
  return tokens.map((line) =>
    line.map((token) => ({ content: token.content, style: token.htmlStyle })),
  );
}
