"use client";

import { LanguagesIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { locales } from "@/i18n/config";
import { useChooseLocale } from "./use-choose-locale";

export function LocaleSwitcher() {
  const t = useTranslations("nav");
  const { locale, chooseLocale, switchingLocale } = useChooseLocale();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="sm" aria-label={t("language")} disabled={switchingLocale}>
            <LanguagesIcon aria-hidden />
            <span className="hidden sm:inline">{t(`languages.${locale}`)}</span>
          </Button>
        }
      />
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuGroup>
          <DropdownMenuLabel>{t("language")}</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={locale} onValueChange={chooseLocale}>
            {locales.map((value) => (
              <DropdownMenuRadioItem key={value} value={value} lang={value} closeOnClick>
                {t(`languages.${value}`)}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
