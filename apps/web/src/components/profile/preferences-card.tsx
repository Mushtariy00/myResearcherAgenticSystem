"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useId } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { locales } from "@/i18n/config";
import { THEMES, usePreferences } from "./use-preferences";

/** One choice: a radio and its name, the whole box clickable. */
function Option({ value, lang, children }: { value: string; lang?: string; children: ReactNode }) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: the Base UI radio inside is the control
    <label
      lang={lang}
      className="flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-sm transition-colors hover:bg-muted/60 has-data-checked:border-primary has-data-checked:bg-primary/5"
    >
      <RadioGroupItem value={value} />
      {children}
    </label>
  );
}

/** The UI language and theme, the same choices as the header's menus. */
export function PreferencesCard() {
  const t = useTranslations();
  const ids = useId();
  const { locale, chooseLocale, switchingLocale, theme, chooseTheme } = usePreferences();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("profile.preferences.title")}</CardTitle>
        <CardDescription>{t("profile.preferences.description")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5">
        <div className="grid gap-2">
          <p id={`${ids}-language`} className="text-sm font-medium">
            {t("profile.preferences.language")}
          </p>
          <RadioGroup
            aria-labelledby={`${ids}-language`}
            value={locale}
            onValueChange={chooseLocale}
            disabled={switchingLocale}
            className="grid-cols-2"
          >
            {locales.map((value) => (
              <Option key={value} value={value} lang={value}>
                {t(`nav.languages.${value}`)}
              </Option>
            ))}
          </RadioGroup>
        </div>
        <div className="grid gap-2">
          <p id={`${ids}-theme`} className="text-sm font-medium">
            {t("profile.preferences.theme")}
          </p>
          <RadioGroup
            aria-labelledby={`${ids}-theme`}
            value={theme}
            onValueChange={chooseTheme}
            className="grid-cols-3"
          >
            {THEMES.map((value) => (
              <Option key={value} value={value}>
                {t(`nav.themes.${value}`)}
              </Option>
            ))}
          </RadioGroup>
        </div>
      </CardContent>
    </Card>
  );
}
