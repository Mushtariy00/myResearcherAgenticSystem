"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { PageHeader } from "@/components/app/query-state";
import { InviteUserCard } from "./invite-user-card";
import { type IssuedLink, LinkDialog } from "./link-dialog";
import { PaidModelsCard } from "./paid-models-card";
import { UsersCard } from "./users-card";

export function AdminView() {
  const t = useTranslations("admin");
  const [link, setLink] = useState<IssuedLink | null>(null);

  return (
    <>
      <PageHeader title={t("title")} description={t("description")} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <UsersCard onIssued={setLink} />
        </div>
        <div className="grid content-start gap-6 md:grid-cols-2 xl:grid-cols-1">
          <InviteUserCard onIssued={setLink} />
          <PaidModelsCard />
        </div>
      </div>
      <LinkDialog link={link} onClose={() => setLink(null)} />
    </>
  );
}
