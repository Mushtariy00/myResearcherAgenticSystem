"use client";

import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useId, useMemo, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { type JsonParseResult, parseJson, toJsonText } from "./json-parse";
import { useElementWidth } from "./use-dom";

const MonacoJsonEditor = dynamic(() => import("./monaco-json-editor"), {
  ssr: false,
  loading: () => (
    <div className="grid gap-2 rounded-lg border p-4">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  ),
});

/** Narrower containers (phones, side panels) keep the plain textarea. */
const MONACO_MIN_WIDTH = 640;

export type JsonEditorProps = {
  /** The JSON text (controlled). Start from `toJsonText(output.data)`. */
  value: string;
  /** Every edit, with the parse result: `result.ok` and `result.value` once the text is valid. */
  onChange: (text: string, result: JsonParseResult) => void;
  /** Accessible name; default "JSON editor". */
  label?: string;
  readOnly?: boolean;
  /** "auto": Monaco (JSON mode, loaded on demand) on wide containers, a textarea otherwise. */
  mode?: "auto" | "monaco" | "textarea";
  /** CSS height of the editing area; default 24rem. */
  height?: string;
  className?: string;
};

/**
 * Editable JSON for approve-with-edits, with live parse errors (line, column and a translated
 * reason) under the editor and a Format button. Validity against the stage schema is checked
 * by the API when the edit is submitted.
 */
export function JsonEditor({
  value,
  onChange,
  label,
  readOnly = false,
  mode = "auto",
  height = "24rem",
  className,
}: JsonEditorProps) {
  const t = useTranslations("shared.json");
  const tErrors = useTranslations("shared.json.errors");
  const container = useRef<HTMLDivElement>(null);
  const width = useElementWidth(container);
  const statusId = useId();
  const result = useMemo(() => parseJson(value), [value]);
  const name = label ?? t("editor");
  const monaco =
    mode === "monaco" || (mode === "auto" && width !== undefined && width >= MONACO_MIN_WIDTH);

  const change = (text: string) => onChange(text, parseJson(text));
  const message = result.ok
    ? t("valid")
    : t("invalid", {
        line: result.error.line,
        column: result.error.column,
        message: tErrors(result.error.code, { character: result.error.character ?? "" }),
      });

  return (
    <div ref={container} data-slot="json-editor" className={cn("grid gap-2", className)}>
      {monaco ? (
        <MonacoJsonEditor
          value={value}
          onChange={change}
          label={name}
          readOnly={readOnly}
          height={height}
        />
      ) : (
        <Textarea
          value={value}
          onChange={(event) => change(event.target.value)}
          readOnly={readOnly}
          aria-label={name}
          aria-invalid={!result.ok || undefined}
          aria-describedby={statusId}
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          autoCorrect="off"
          wrap="off"
          className="field-sizing-fixed resize-y font-mono text-xs leading-5"
          style={{ height }}
        />
      )}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p
          id={statusId}
          role="status"
          className={cn(
            "flex min-w-0 items-start gap-1.5 text-xs",
            result.ok ? "text-muted-foreground" : "text-destructive",
          )}
        >
          {result.ok ? (
            <CircleCheckIcon aria-hidden className="mt-px size-3.5 shrink-0" />
          ) : (
            <CircleAlertIcon aria-hidden className="mt-px size-3.5 shrink-0" />
          )}
          <span className="break-words">{message}</span>
        </p>
        {!readOnly && (
          <Button
            type="button"
            size="xs"
            variant="outline"
            disabled={!result.ok}
            onClick={() => {
              if (result.ok) {
                const formatted = toJsonText(result.value);
                onChange(formatted, { ok: true, value: result.value });
              }
            }}
          >
            {t("format")}
          </Button>
        )}
      </div>
    </div>
  );
}
