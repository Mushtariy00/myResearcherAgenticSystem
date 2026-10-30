"use client";

import { useQuery } from "@tanstack/react-query";
import { WalletIcon } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import { listBudgetsOptions } from "@/client/@tanstack/react-query.gen";
import { budgetUse } from "@/components/admin/admin-format";
import { BudgetEditor } from "@/components/admin/budget-editor";
import { authErrorOf, displayName, useLabUsers } from "@/components/admin/use-lab-users";
import { usePaidModels } from "@/components/admin/use-paid-models";
import { QueryError } from "@/components/app/query-state";
import { Switch } from "@/components/ui/switch";
import { authErrorKey } from "@/lib/auth-client";
import { USD } from "@/lib/format";
import { FormAlert } from "@/studio/components/auth/form-alert";
import { PulseDot } from "@/studio/components/effects/pulse-dot";
import { LoadingStatus, ShimmerSkeleton } from "@/studio/components/effects/shimmer-skeleton";
import { StudioSection } from "@/studio/components/profile/studio-section";
import { StudioStatePanel } from "@/studio/components/studio-state-panel";

function PaidModelsSwitch() {
  const t = useTranslations("admin.paidModels");
  const id = useId();
  const { setting, pending, setEnabled } = usePaidModels();

  if (setting.isPending) {
    return <ShimmerSkeleton className="h-6 w-48" />;
  }
  if (setting.isError) {
    return <QueryError error={setting.error} onRetry={() => setting.refetch()} />;
  }
  return (
    <div className="flex items-center gap-3">
      <Switch
        id={id}
        checked={setting.data.enabled}
        disabled={pending}
        onCheckedChange={setEnabled}
      />
      <label htmlFor={id} className="flex items-center gap-2 text-sm text-foreground">
        <PulseDot tone={setting.data.enabled ? "success" : "danger"} />
        {setting.data.enabled ? t("on") : t("off")}
      </label>
    </div>
  );
}

/** Studio budgets: every member's monthly budget edited inline, and the paid-models switch. */
export function StudioBudgetsPanel() {
  const t = useTranslations("admin");
  const te = useTranslations("auth.errors");
  const tCommon = useTranslations("common");
  const format = useFormatter();
  const users = useLabUsers();
  const budgets = useQuery(listBudgetsOptions());
  const budgetByUser = new Map((budgets.data ?? []).map((budget) => [budget.user_id, budget]));

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <StudioSection
        id="studio-admin-budgets"
        title={t("budgets.title")}
        description={t("budgets.description")}
      >
        {budgets.isError && <QueryError error={budgets.error} onRetry={() => budgets.refetch()} />}
        {users.isPending ? (
          <div className="grid gap-2" aria-busy="true">
            <LoadingStatus label={tCommon("loading")} />
            {Array.from({ length: 4 }, (_, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders never reorder
              <ShimmerSkeleton key={index} className="h-16 rounded-xl" />
            ))}
          </div>
        ) : users.isError ? (
          <FormAlert message={te(authErrorKey(authErrorOf(users.error)))} />
        ) : users.data.length === 0 ? (
          <StudioStatePanel
            variant="section"
            icon={<WalletIcon aria-hidden />}
            title={t("budgets.empty")}
            description={t("budgets.description")}
          />
        ) : (
          <ul className="grid gap-2">
            <li
              aria-hidden
              className="hidden px-3 text-xs font-medium text-muted-foreground sm:grid sm:grid-cols-[minmax(0,1fr)_auto_7rem] sm:gap-3"
            >
              <span>{t("budgets.user")}</span>
              <span className="w-[10.5rem]">{t("budgets.budget")}</span>
              <span className="text-right">{t("budgets.spent")}</span>
            </li>
            {users.data.map((user) => {
              const budget = budgetByUser.get(user.id);
              const use = budgetUse(budget);
              const name = displayName(user);
              return (
                <li
                  key={user.id}
                  className="grid gap-3 rounded-xl border border-(--studio-glass-border) bg-(--studio-glass) px-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto_7rem] sm:items-center"
                >
                  <div className="grid min-w-0 gap-1.5">
                    <p className="truncate text-sm font-medium text-foreground">{name}</p>
                    {use.monthly > 0 ? (
                      <div
                        role="progressbar"
                        aria-label={t("budgets.usedFor", { name })}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={Math.round(use.percent)}
                        className="h-1.5 w-full max-w-64 overflow-hidden rounded-full bg-(--studio-glass-strong)"
                      >
                        <div
                          data-tone={use.tone}
                          className="h-full origin-left rounded-full bg-(--tone) transition-transform duration-700 ease-out motion-reduce:transition-none"
                          style={{ transform: `scaleX(${use.percent / 100})` }}
                        />
                      </div>
                    ) : (
                      <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                    )}
                  </div>
                  {budgets.isPending ? (
                    <ShimmerSkeleton className="h-9 w-36" />
                  ) : (
                    <BudgetEditor
                      key={budget?.monthly_usd ?? "none"}
                      userId={user.id}
                      userName={name}
                      budget={budget}
                      inputClassName="h-9 w-28 rounded-[10px] border-(--studio-glass-border) bg-(--studio-glass) dark:bg-(--studio-glass)"
                      buttonClassName="size-9 rounded-[10px]"
                    />
                  )}
                  <p className="text-sm text-muted-foreground tabular-nums sm:text-right">
                    <span className="sr-only">{t("budgets.spent")}: </span>
                    <span className="font-medium text-foreground">
                      {format.number(use.spent, USD)}
                    </span>
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </StudioSection>
      <StudioSection
        id="studio-admin-paid-models"
        title={t("paidModels.title")}
        description={t("paidModels.description")}
        className="h-fit"
      >
        <PaidModelsSwitch />
      </StudioSection>
    </div>
  );
}
