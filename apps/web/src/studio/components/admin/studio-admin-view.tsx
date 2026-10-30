"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { ADMIN_TAB_ICONS, ADMIN_TABS, type AdminTab } from "@/components/admin/admin-sections";
import { type IssuedLink, LinkDialog } from "@/components/admin/link-dialog";
import { useAdminTab } from "@/components/admin/use-admin-tab";
import { useCurrentUser } from "@/components/app/current-user";
import {
  AnimatedTabs,
  AnimatedTabsList,
  AnimatedTabsPanel,
  AnimatedTabsTab,
} from "@/studio/components/effects/animated-tabs";
import { StudioAuditPanel } from "./studio-audit-panel";
import { StudioBalancePanel } from "./studio-balance-panel";
import { StudioBudgetsPanel } from "./studio-budgets-panel";
import { StudioHealthPanel } from "./studio-health-panel";
import { StudioRoutingPanel } from "./studio-routing-panel";
import { StudioUsersPanel } from "./studio-users-panel";

/**
 * The Studio admin page (lab admins only; the page returns not-found to anyone else): the
 * same six sections as Classic, as animated tabs whose choice is kept in `?tab=`. Only the
 * open tab loads its data.
 */
export function StudioAdminView({ initialTab }: { initialTab: AdminTab }) {
  const t = useTranslations("admin");
  const user = useCurrentUser();
  const [tab, setTab] = useAdminTab(initialTab);
  const [link, setLink] = useState<IssuedLink | null>(null);

  // The page already refuses everyone else; this keeps the tabs from ever rendering for them.
  if (user.role !== "admin") {
    return null;
  }

  return (
    <div className="grid gap-8">
      <header className="studio-rise grid gap-2">
        <h1 className="studio-display text-3xl text-foreground sm:text-4xl">{t("title")}</h1>
        <p className="text-base text-muted-foreground">{t("description")}</p>
      </header>
      <AnimatedTabs value={tab} onValueChange={setTab} className="grid gap-6">
        <AnimatedTabsList aria-label={t("tabs.label")} className="w-full sm:w-fit">
          {ADMIN_TABS.map((value) => {
            const Icon = ADMIN_TAB_ICONS[value];
            return (
              <AnimatedTabsTab key={value} value={value}>
                <Icon aria-hidden />
                {t(`tabs.${value}`)}
              </AnimatedTabsTab>
            );
          })}
        </AnimatedTabsList>
        <AnimatedTabsPanel value="users" className="rounded-2xl">
          <StudioUsersPanel onIssued={setLink} />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="budgets" className="rounded-2xl">
          <StudioBudgetsPanel />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="routing" className="rounded-2xl">
          <StudioRoutingPanel />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="balance" className="rounded-2xl">
          <StudioBalancePanel />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="health" className="rounded-2xl">
          <StudioHealthPanel />
        </AnimatedTabsPanel>
        <AnimatedTabsPanel value="audit" className="rounded-2xl">
          <StudioAuditPanel />
        </AnimatedTabsPanel>
      </AnimatedTabs>
      <LinkDialog link={link} onClose={() => setLink(null)} />
    </div>
  );
}
