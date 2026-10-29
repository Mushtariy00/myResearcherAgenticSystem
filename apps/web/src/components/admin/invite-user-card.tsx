"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertCircleIcon, SendIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState, useTransition } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { inviteUser } from "@/lib/admin-actions";
import { authErrorKey } from "@/lib/auth-client";
import type { IssuedLink } from "./link-dialog";
import { ADMIN_USERS_QUERY_KEY } from "./users-card";

const LAB_ROLES = ["user", "admin"] as const;
type LabRole = (typeof LAB_ROLES)[number];

export function InviteUserCard({ onIssued }: { onIssued: (link: IssuedLink) => void }) {
  const t = useTranslations("admin.invite");
  const tr = useTranslations("roles");
  const te = useTranslations("auth.errors");
  const queryClient = useQueryClient();
  const ids = useId();
  const [role, setRole] = useState<LabRole>("user");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const name = String(form.get("name") ?? "").trim();
    const email = String(form.get("email") ?? "").trim();
    setError(null);
    startTransition(async () => {
      const result = await inviteUser({ name, email, role });
      if (!result.ok) {
        setError(te(authErrorKey({ code: result.code })));
        return;
      }
      formElement.reset();
      setRole("user");
      await queryClient.invalidateQueries({ queryKey: ADMIN_USERS_QUERY_KEY });
      onIssued({
        email: email.toLowerCase(),
        url: result.url,
        emailed: result.emailed,
        kind: "invite",
      });
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4">
          {error && (
            <Alert variant="destructive">
              <AlertCircleIcon aria-hidden />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <div className="grid gap-2">
            <Label htmlFor={`${ids}-name`}>{t("name")}</Label>
            <Input id={`${ids}-name`} name="name" required maxLength={200} autoComplete="off" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`${ids}-email`}>{t("email")}</Label>
            <Input
              id={`${ids}-email`}
              name="email"
              type="email"
              required
              maxLength={320}
              autoComplete="off"
            />
          </div>
          <div className="grid gap-2">
            <Label id={`${ids}-role`}>{t("role")}</Label>
            <Select
              items={Object.fromEntries(LAB_ROLES.map((value) => [value, tr(value)]))}
              value={role}
              onValueChange={(value) => setRole(value === "admin" ? "admin" : "user")}
            >
              <SelectTrigger className="w-full" aria-labelledby={`${ids}-role`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LAB_ROLES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {tr(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={pending}>
            <SendIcon aria-hidden />
            {pending ? t("sending") : t("submit")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
