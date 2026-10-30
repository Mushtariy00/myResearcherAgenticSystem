"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { authClient } from "@/lib/auth-client";
import { STUDIO_LOGIN_PATH } from "@/studio/lib/login-redirect";

/**
 * Signs out and lands on the Studio sign-in page. Same steps as the Classic user menu
 * (src/components/app/user-menu.tsx), which always returns to the Classic sign-in page.
 */
export function useStudioSignOut() {
  const t = useTranslations("nav");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [signingOut, setSigningOut] = useState(false);

  const signOut = useCallback(async () => {
    setSigningOut(true);
    const { error } = await authClient.signOut();
    if (error) {
      setSigningOut(false);
      toast.error(t("signOutFailed"));
      return;
    }
    queryClient.clear();
    router.replace(STUDIO_LOGIN_PATH);
    router.refresh();
  }, [queryClient, router, t]);

  return { signOut, signingOut };
}
