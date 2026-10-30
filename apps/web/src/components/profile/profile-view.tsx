"use client";

import { useTranslations } from "next-intl";
import { useCurrentUser } from "@/components/app/current-user";
import { PageHeader } from "@/components/app/query-state";
import { RoleBadge } from "@/components/app/status-badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmailNotificationsCard } from "./email-notifications-card";
import { PasswordCard } from "./password-card";
import { PreferencesCard } from "./preferences-card";
import { ProjectsCard } from "./projects-card";
import { SessionsCard } from "./sessions-card";
import { UsageCard } from "./usage-card";

/** Who I am in the lab: name, email and lab role (from the session). */
function AccountCard() {
  const t = useTranslations("profile.account");
  const user = useCurrentUser();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]">
          <dt className="text-muted-foreground">{t("name")}</dt>
          <dd className="font-medium break-words">{user.name || t("noName")}</dd>
          <dt className="text-muted-foreground">{t("email")}</dt>
          <dd className="font-medium break-all">{user.email}</dd>
          <dt className="text-muted-foreground">{t("labRole")}</dt>
          <dd>
            <RoleBadge role={user.role} />
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}

/**
 * The Classic profile page: my account, password and other devices, language and theme,
 * notification emails, my budget and LLM use, and my projects with my role in each.
 */
export function ProfileView() {
  const t = useTranslations("profile");
  return (
    <>
      <PageHeader title={t("title")} description={t("description")} />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="grid content-start gap-6">
          <AccountCard />
          <PreferencesCard />
          <EmailNotificationsCard />
          <PasswordCard />
          <SessionsCard />
        </div>
        <div className="grid content-start gap-6">
          <UsageCard />
          <ProjectsCard />
        </div>
      </div>
    </>
  );
}
