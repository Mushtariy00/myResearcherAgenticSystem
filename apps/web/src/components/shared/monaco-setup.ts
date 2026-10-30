"use client";

/**
 * Monaco from the local monaco-editor package (never the CDN default of @monaco-editor/react):
 * the editor core, its standard features, syntax colouring for the languages generated code
 * uses, and JSON language support. Workers are bundled from local entry files. Only the lazily
 * loaded editor chunks import this module.
 */
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor";
import "monaco-editor/features/register.all";
import "monaco-editor/languages/definitions/ini/register";
import "monaco-editor/languages/definitions/markdown/register";
import "monaco-editor/languages/definitions/python/register";
import "monaco-editor/languages/definitions/shell/register";
import "monaco-editor/languages/definitions/yaml/register";
import "monaco-editor/languages/features/json/register";
import { resolveColors, toHex } from "./css-color";

if (typeof window !== "undefined") {
  globalThis.MonacoEnvironment = {
    getWorker: (_workerId: string, label: string) =>
      label === "json"
        ? new Worker(new URL("./workers/monaco-json.worker.ts", import.meta.url), {
            type: "module",
            name: label,
          })
        : new Worker(new URL("./workers/monaco-editor.worker.ts", import.meta.url), {
            type: "module",
            name: label,
          }),
  };
}

loader.config({ monaco });

export { monaco };

const LANGUAGES: Record<string, string> = {
  python: "python",
  py: "python",
  yaml: "yaml",
  yml: "yaml",
  markdown: "markdown",
  md: "markdown",
  json: "json",
  bash: "shell",
  sh: "shell",
  shell: "shell",
  zsh: "shell",
  toml: "ini",
  ini: "ini",
};

/** Monaco language id for a CodeFile language or file extension. */
export function monacoLanguage(language: string | null | undefined, path?: string): string {
  const declared = language?.trim().toLowerCase();
  const extension = path?.split(".").pop()?.toLowerCase();
  return (declared && LANGUAGES[declared]) || (extension && LANGUAGES[extension]) || "plaintext";
}

/**
 * Defines (or redefines) the editor theme from the CSS tokens in scope, so Monaco's surfaces
 * match the card it sits on in Classic, dark mode or Studio. Returns the theme name.
 */
export function applyMonacoTheme(scope: HTMLElement | null, dark: boolean): string {
  const name = dark ? "arp-dark" : "arp-light";
  const colors = scope
    ? resolveColors(scope, {
        background: "var(--card, Canvas)",
        foreground: "var(--card-foreground, CanvasText)",
        muted: "var(--muted-foreground, GrayText)",
        border: "var(--border, GrayText)",
        popover: "var(--popover, Canvas)",
      })
    : undefined;
  monaco.editor.defineTheme(name, {
    base: dark ? "vs-dark" : "vs",
    inherit: true,
    rules: [],
    colors: colors
      ? {
          "editor.background": toHex(colors.background),
          "editorGutter.background": toHex(colors.background),
          "editor.foreground": toHex(colors.foreground),
          "editorLineNumber.foreground": toHex(colors.muted),
          "editorLineNumber.activeForeground": toHex(colors.foreground),
          "editorWidget.background": toHex(colors.popover),
          "editorWidget.border": toHex(colors.border),
        }
      : {},
  });
  monaco.editor.setTheme(name);
  return name;
}
