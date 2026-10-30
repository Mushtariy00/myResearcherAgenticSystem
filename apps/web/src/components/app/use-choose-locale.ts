"use client";

import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { useTransition } from "react";
import { useUpdateMySettings } from "@/hooks/use-my-settings";
import { setLocale } from "@/i18n/actions";
import { isLocale, type Locale } from "@/i18n/config";
import { useSignedInUser } from "./current-user";

/**
 * Switches the UI language, for every language switch of both interfaces: the cookie decides
 * the UI, and a refresh re-renders the page in it. A signed-in user's choice is also saved as
 * the language of their notification emails, so the emails follow the UI.
 */
export function useChooseLocale() {
  const locale = useLocale() as Locale;
  const router = useRouter();
  const signedIn = useSignedInUser() !== null;
  const { mutate: saveSettings } = useUpdateMySettings();
  const [pending, startTransition] = useTransition();

  function chooseLocale(value: unknown) {
    if (!isLocale(value) || value === locale) {
      return;
    }
    if (signedIn) {
      saveSettings({ body: { locale: value } });
    }
    startTransition(async () => {
      await setLocale(value);
      router.refresh();
    });
  }

  return { locale, chooseLocale, switchingLocale: pending };
}
