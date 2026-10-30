"use client";

import { LanguagesIcon, type LucideIcon, MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useId } from "react";
import { THEMES, usePreferences } from "@/components/profile/use-preferences";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { locales } from "@/i18n/config";

const THEME_ICONS = { light: SunIcon, dark: MoonIcon, system: MonitorIcon } as const;

/** One choice as a glass tile: a radio, an icon and its name, the whole tile clickable. */
function Option({
  value,
  icon: Icon,
  lang,
  children,
}: {
  value: string;
  icon: LucideIcon;
  lang?: string;
  children: ReactNode;
}) {
  return (
    // biome-ignore lint/a11y/noLabelWithoutControl: the Base UI radio inside is the control
    <label
      lang={lang}
      className="flex cursor-pointer items-center gap-2.5 rounded-[10px] border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-2.5 text-sm text-foreground shadow-[inset_0_1px_0_0_var(--studio-glass-highlight)] transition-colors hover:bg-(--studio-hover) has-data-checked:border-(--studio-accent-fg)/50 has-data-checked:bg-(--studio-hover)"
    >
      <RadioGroupItem value={value} />
      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      {children}
    </label>
  );
}

/** Language and theme in Studio: the same choices and storage as Classic. */
export function StudioPreferences() {
  const t = useTranslations();
  const ids = useId();
  const { locale, chooseLocale, switchingLocale, theme, chooseTheme } = usePreferences();

  return (
    <div className="grid gap-5">
      <div className="grid gap-2">
        <p id={`${ids}-language`} className="text-sm font-medium text-foreground">
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
            <Option key={value} value={value} icon={LanguagesIcon} lang={value}>
              {t(`nav.languages.${value}`)}
            </Option>
          ))}
        </RadioGroup>
      </div>
      <div className="grid gap-2">
        <p id={`${ids}-theme`} className="text-sm font-medium text-foreground">
          {t("profile.preferences.theme")}
        </p>
        <RadioGroup
          aria-labelledby={`${ids}-theme`}
          value={theme}
          onValueChange={chooseTheme}
          className="grid-cols-1 sm:grid-cols-3"
        >
          {THEMES.map((value) => (
            <Option key={value} value={value} icon={THEME_ICONS[value]}>
              {t(`nav.themes.${value}`)}
            </Option>
          ))}
        </RadioGroup>
      </div>
    </div>
  );
}
