"use client";

import { Tabs } from "@base-ui/react/tabs";
import { useTranslations } from "next-intl";
import { type ReactNode, useState } from "react";
import { useCurrentUser } from "@/components/app/current-user";
import { PageHeader } from "@/components/app/query-state";
import { ADMIN_TAB_ICONS, ADMIN_TABS, type AdminTab } from "./admin-sections";
import { AuditLogCard } from "./audit-log-card";
import { BudgetsCard } from "./budgets-card";
import { InviteUserCard } from "./invite-user-card";
import { LabBalanceCard } from "./lab-balance-card";
import { type IssuedLink, LinkDialog } from "./link-dialog";
import { ModelRoutingCard } from "./model-routing-card";
import { PaidModelsCard } from "./paid-models-card";
import { SystemHealthCard } from "./system-health-card";
import { useAdminTab } from "./use-admin-tab";
import { UsersCard } from "./users-card";

function Panel({ value, children }: { value: AdminTab; children: ReactNode }) {
  return (
    <Tabs.Panel
      value={value}
      className="rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      {children}
    </Tabs.Panel>
  );
}

/**
 * The Classic admin page (lab admins only; the page returns not-found to anyone else): users
 * and invites, budgets and the paid-models switch, model routing, the lab balance, system
 * health and the audit log, one tab each. Only the open tab loads its data.
 */
export function AdminView({ initialTab }: { initialTab: AdminTab }) {
  const t = useTranslations("admin");
  const user = useCurrentUser();
  const [tab, setTab] = useAdminTab(initialTab);
  const [link, setLink] = useState<IssuedLink | null>(null);

  // The page already refuses everyone else; this keeps the tabs from ever rendering for them.
  if (user.role !== "admin") {
    return null;
  }

  return (
    <>
      <PageHeader title={t("title")} description={t("description")} />
      <Tabs.Root
        value={tab}
        onValueChange={(value) => {
          if (typeof value === "string") {
            setTab(value);
          }
        }}
        className="grid gap-6"
      >
        <Tabs.List
          aria-label={t("tabs.label")}
          className="-mx-4 flex gap-1 overflow-x-auto border-b px-4 sm:mx-0 sm:px-0"
        >
          {ADMIN_TABS.map((value) => {
            const Icon = ADMIN_TAB_ICONS[value];
            return (
              <Tabs.Tab
                key={value}
                value={value}
                className="-mb-px inline-flex h-9 shrink-0 items-center gap-1.5 border-b-2 border-transparent px-3 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:rounded-md focus-visible:ring-3 focus-visible:ring-ring/50 data-active:border-primary data-active:text-foreground [&_svg]:size-4 [&_svg]:shrink-0"
              >
                <Icon aria-hidden />
                {t(`tabs.${value}`)}
              </Tabs.Tab>
            );
          })}
        </Tabs.List>
        <Panel value="users">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="min-w-0">
              <UsersCard onIssued={setLink} />
            </div>
            <div className="min-w-0">
              <InviteUserCard onIssued={setLink} />
            </div>
          </div>
        </Panel>
        <Panel value="budgets">
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="min-w-0">
              <BudgetsCard />
            </div>
            <div className="min-w-0">
              <PaidModelsCard />
            </div>
          </div>
        </Panel>
        <Panel value="routing">
          <ModelRoutingCard />
        </Panel>
        <Panel value="balance">
          <LabBalanceCard />
        </Panel>
        <Panel value="health">
          <SystemHealthCard />
        </Panel>
        <Panel value="audit">
          <AuditLogCard />
        </Panel>
      </Tabs.Root>
      <LinkDialog link={link} onClose={() => setLink(null)} />
    </>
  );
}
