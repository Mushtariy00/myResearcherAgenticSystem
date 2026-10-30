"use client";

import { AlertCircleIcon, SendIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId } from "react";
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
import type { IssuedLink } from "./link-dialog";
import { LAB_ROLES, useInviteUser } from "./use-invite-user";

export function InviteUserCard({ onIssued }: { onIssued: (link: IssuedLink) => void }) {
  const t = useTranslations("admin.invite");
  const tr = useTranslations("roles");
  const ids = useId();
  const { role, setRole, error, pending, onSubmit } = useInviteUser(onIssued);

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
              onValueChange={setRole}
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
