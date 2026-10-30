"use client";

import { DiffEditor } from "@monaco-editor/react";
import { useTranslations } from "next-intl";
import { useLayoutEffect, useRef, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { applyMonacoTheme, monacoLanguage } from "./monaco-setup";
import { useIsDark, useThemeKey } from "./use-dom";

export type MonacoDiffEditorProps = {
  original: string;
  modified: string;
  language?: string | null;
  path?: string;
  /** Accessible name of the editor. */
  label: string;
  height: string;
};

/** Read-only side-by-side diff (loaded on demand; see CodeDiff for the lightweight fallback). */
export default function MonacoDiffEditor({
  original,
  modified,
  language,
  path,
  label,
  height,
}: MonacoDiffEditorProps) {
  const t = useTranslations("shared.diff");
  const scope = useRef<HTMLDivElement>(null);
  const dark = useIsDark();
  const themeKey = useThemeKey();
  const [theme, setTheme] = useState(dark ? "arp-dark" : "arp-light");

  // biome-ignore lint/correctness/useExhaustiveDependencies: themeKey signals token changes
  useLayoutEffect(() => {
    setTheme(applyMonacoTheme(scope.current, dark));
  }, [dark, themeKey]);

  return (
    <div ref={scope} data-slot="monaco-diff" className="overflow-hidden">
      <DiffEditor
        original={original}
        modified={modified}
        language={monacoLanguage(language, path)}
        theme={theme}
        height={height}
        beforeMount={() => applyMonacoTheme(scope.current, dark)}
        loading={
          <div className="grid w-full gap-2 p-4" role="status">
            <span className="sr-only">{t("loadingEditor")}</span>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        }
        options={{
          readOnly: true,
          originalEditable: false,
          domReadOnly: true,
          renderSideBySide: true,
          useInlineViewWhenSpaceIsLimited: true,
          hideUnchangedRegions: { enabled: true },
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          renderOverviewRuler: false,
          automaticLayout: true,
          fontSize: 12,
          lineHeight: 20,
          ariaLabel: label,
        }}
      />
    </div>
  );
}
