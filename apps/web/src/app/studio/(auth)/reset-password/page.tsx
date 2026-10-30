import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { MIN_PASSWORD_LENGTH } from "@/lib/password-policy";
import { StudioResetPasswordForm } from "@/studio/components/auth/studio-reset-password-form";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.reset");
  return { title: t("title") };
}

/**
 * The Studio twin of /reset-password: `?token=...` once Better Auth checked the link
 * (`?error=INVALID_TOKEN` when it is unknown or expired).
 */
export default async function StudioResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { token, error } = await searchParams;
  const valid = typeof token === "string" && token.length > 0 && !error;
  return <StudioResetPasswordForm token={valid ? token : null} minLength={MIN_PASSWORD_LENGTH} />;
}
