"use client";

import { AlertCircleIcon, CircleCheckIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { useCurrentUser } from "@/components/app/current-user";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH } from "@/lib/password-policy";
import {
  PASSWORD_FIELDS,
  type PasswordField,
  useChangePasswordForm,
} from "./use-change-password-form";

/** Change your password: the current one, the new one twice, and optionally sign out elsewhere. */
export function PasswordCard() {
  const t = useTranslations();
  const user = useCurrentUser();
  const ids = useId();
  const { pending, problem, problemText, done, onSubmit } = useChangePasswordForm();
  const problemId = `${ids}-problem`;
  const hintId = `${ids}-hint`;

  /** aria props of a field: invalid and described by the problem when it is the one to fix. */
  function fieldProps(field: PasswordField) {
    const invalid = problem?.field === field;
    return {
      id: `${ids}-${field}`,
      name: PASSWORD_FIELDS[field],
      "aria-invalid": invalid || undefined,
      "aria-describedby":
        [invalid ? problemId : null, field === "new" ? hintId : null].filter(Boolean).join(" ") ||
        undefined,
    };
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("profile.password.title")}</CardTitle>
        <CardDescription>{t("profile.password.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate className="grid gap-4">
          {problemText && (
            <Alert variant="destructive" id={problemId}>
              <AlertCircleIcon aria-hidden />
              <AlertTitle>{t("profile.password.failed")}</AlertTitle>
              <AlertDescription>{problemText}</AlertDescription>
            </Alert>
          )}
          {done && (
            <Alert role="status">
              <CircleCheckIcon aria-hidden />
              <AlertDescription>
                {done.signedOutOthers
                  ? t("profile.password.doneSignedOut")
                  : t("profile.password.done")}
              </AlertDescription>
            </Alert>
          )}
          {/* Lets password managers file the new password under the right account. */}
          <input
            type="text"
            name="username"
            autoComplete="username"
            value={user.email}
            readOnly
            hidden
          />
          <div className="grid gap-2">
            <Label htmlFor={`${ids}-current`}>{t("profile.password.current")}</Label>
            <Input
              {...fieldProps("current")}
              type="password"
              autoComplete="current-password"
              maxLength={MAX_PASSWORD_LENGTH}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`${ids}-new`}>{t("auth.fields.newPassword")}</Label>
            <Input
              {...fieldProps("new")}
              type="password"
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              maxLength={MAX_PASSWORD_LENGTH}
              required
            />
            <p id={hintId} className="text-xs text-muted-foreground">
              {t("auth.reset.hint", { min: MIN_PASSWORD_LENGTH })}
            </p>
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`${ids}-confirm`}>{t("auth.fields.confirmPassword")}</Label>
            <Input
              {...fieldProps("confirm")}
              type="password"
              autoComplete="new-password"
              maxLength={MAX_PASSWORD_LENGTH}
              required
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="signOutOthers"
              defaultChecked
              className="size-4 rounded accent-primary focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            />
            {t("profile.password.signOutOthers")}
          </label>
          <Button type="submit" disabled={pending} className="w-fit">
            {pending ? t("profile.password.submitting") : t("profile.password.submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
