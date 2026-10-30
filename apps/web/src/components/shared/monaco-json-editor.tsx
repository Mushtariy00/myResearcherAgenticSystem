"use client";

import Editor from "@monaco-editor/react";
import { useTranslations } from "next-intl";
import { useLayoutEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { applyMonacoTheme } from "./monaco-setup";
import { useIsDark, useThemeKey } from "./use-dom";

export type MonacoJsonEditorProps = {
  value: string;
  onChange: (text: string) => void;
  /** Accessible name of the editor. */
  label: string;
  readOnly?: boolean;
  height: string;
};

/** Monaco in JSON mode (loaded on demand; JsonEditor falls back to a textarea). */
export default function MonacoJsonEditor({
  value,
  onChange,
  label,
  readOnly = false,
  height,
}: MonacoJsonEditorProps) {
  const t = useTranslations("shared.json");
  const scope = useRef<HTMLDivElement>(null);
  const dark = useIsDark();
  const themeKey = useThemeKey();
  const [theme, setTheme] = useState(dark ? "arp-dark" : "arp-light");

  // biome-ignore lint/correctness/useExhaustiveDependencies: themeKey signals token changes
  useLayoutEffect(() => {
    setTheme(applyMonacoTheme(scope.current, dark));
  }, [dark, themeKey]);

  return (
    <div ref={scope} data-slot="monaco-json" className="overflow-hidden rounded-lg border">
      <Editor
        value={value}
        language="json"
        theme={theme}
        height={height}
        onChange={(next) => onChange(next ?? "")}
        beforeMount={() => applyMonacoTheme(scope.current, dark)}
        loading={
          <div className="grid w-full gap-2 p-4" role="status">
            <span className="sr-only">{t("loadingEditor")}</span>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        }
        options={{
          readOnly,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          insertSpaces: true,
          wordWrap: "on",
          fontSize: 12,
          lineHeight: 20,
          ariaLabel: label,
        }}
      />
    </div>
  );
}
