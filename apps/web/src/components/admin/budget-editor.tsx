"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { SaveIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { toast } from "sonner";
import type { BudgetOut } from "@/client";
import { listBudgetsQueryKey, setBudgetMutation } from "@/client/@tanstack/react-query.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useErrorMessage } from "@/hooks/use-error-message";
import { toAmount } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The API takes monthly budgets from $0 to $10,000. */
const MAX_BUDGET_USD = 10_000;

export type BudgetEditorProps = {
  userId: string;
  /** For the accessible names ("Monthly budget for Ada"). */
  userName: string;
  budget: BudgetOut | undefined;
  /** Restyle the field and the save button (Studio). */
  inputClassName?: string;
  buttonClassName?: string;
};

/**
 * Inline editing of one person's monthly budget, in both interfaces. Key it by the saved
 * amount so a new value from the server resets the field.
 */
export function BudgetEditor({
  userId,
  userName,
  budget,
  inputClassName,
  buttonClassName,
}: BudgetEditorProps) {
  const t = useTranslations("admin.budgets");
  const errorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const id = useId();
  const initial = String(toAmount(budget?.monthly_usd));
  const [value, setValue] = useState(initial);
  const save = useMutation({
    ...setBudgetMutation(),
    onSuccess: async () => {
      toast.success(t("saved"));
      await queryClient.invalidateQueries({ queryKey: listBudgetsQueryKey() });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate({ path: { user_id: userId }, body: { monthly_usd: value.trim() || "0" } });
  }

  return (
    <form onSubmit={onSubmit} className="flex items-center gap-1.5">
      <label htmlFor={id} className="sr-only">
        {t("budgetFor", { name: userName })}
      </label>
      <span aria-hidden className="text-muted-foreground">
        $
      </span>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        max={MAX_BUDGET_USD}
        step="0.01"
        required
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className={cn("h-7 w-24 tabular-nums", inputClassName)}
      />
      <Button
        type="submit"
        size="icon-sm"
        variant="outline"
        disabled={save.isPending || value === initial}
        aria-label={t("saveFor", { name: userName })}
        title={t("save")}
        className={buttonClassName}
      >
        <SaveIcon aria-hidden />
      </Button>
    </form>
  );
}
