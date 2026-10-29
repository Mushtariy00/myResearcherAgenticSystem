import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { ResetPasswordForm } from "@/components/auth/reset-password-form";
import { MIN_PASSWORD_LENGTH } from "@/lib/password-policy";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.reset");
  return { title: t("title") };
}

/**
 * Invite and reset links land here as `/reset-password?token=...` after Better Auth checked the
 * token (`?error=INVALID_TOKEN` when it is unknown or expired).
 */
export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { token, error } = await searchParams;
  const valid = typeof token === "string" && token.length > 0 && !error;
  return <ResetPasswordForm token={valid ? token : null} minLength={MIN_PASSWORD_LENGTH} />;
}
