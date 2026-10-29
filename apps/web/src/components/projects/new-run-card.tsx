"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircleIcon, PlayIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { toast } from "sonner";
import type { LlmPolicy } from "@/client";
import { createRunMutation, listRunsQueryKey } from "@/client/@tanstack/react-query.gen";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { useErrorMessage } from "@/hooks/use-error-message";

const POLICIES: readonly LlmPolicy[] = ["auto", "free"];

export function NewRunCard({ projectId }: { projectId: string }) {
  const t = useTranslations("project.newRun");
  const errorMessage = useErrorMessage();
  const router = useRouter();
  const queryClient = useQueryClient();
  const ids = useId();
  const [policy, setPolicy] = useState<LlmPolicy>("auto");
  const create = useMutation({
    ...createRunMutation(),
    onSuccess: async (run) => {
      await queryClient.invalidateQueries({
        queryKey: listRunsQueryKey({ path: { project_id: projectId } }),
      });
      toast.success(t("started"));
      router.push(`/runs/${run.id}`);
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const cap = String(form.get("cap") ?? "").trim();
    create.mutate({
      path: { project_id: projectId },
      body: {
        topic: String(form.get("topic") ?? "").trim(),
        llm_policy: policy,
        budget_cap_usd: cap === "" ? null : cap,
      },
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>{t("description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-5">
          {create.isError && (
            <Alert variant="destructive">
              <AlertCircleIcon aria-hidden />
              <AlertDescription>{errorMessage(create.error)}</AlertDescription>
            </Alert>
          )}
          <div className="grid gap-2">
            <Label htmlFor={`${ids}-topic`}>{t("topic")}</Label>
            <Textarea
              id={`${ids}-topic`}
              name="topic"
              required
              minLength={3}
              maxLength={500}
              rows={2}
              placeholder={t("topicPlaceholder")}
            />
          </div>
          <div className="grid gap-2">
            <p id={`${ids}-policy`} className="text-sm font-medium">
              {t("policy")}
            </p>
            <RadioGroup
              aria-labelledby={`${ids}-policy`}
              value={policy}
              onValueChange={(value) => setPolicy(value === "free" ? "free" : "auto")}
              className="grid gap-2 sm:grid-cols-2"
            >
              {POLICIES.map((value) => (
                <Label
                  key={value}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 font-normal has-data-checked:border-primary has-data-checked:bg-muted/50"
                >
                  {/* Base UI renders the radio as a span, so name it explicitly for screen readers. */}
                  <RadioGroupItem
                    value={value}
                    className="mt-0.5"
                    aria-labelledby={`${ids}-${value}-label`}
                    aria-describedby={`${ids}-${value}-description`}
                  />
                  <span className="grid gap-1">
                    <span id={`${ids}-${value}-label`} className="font-medium">
                      {t(`policies.${value}.label`)}
                    </span>
                    <span
                      id={`${ids}-${value}-description`}
                      className="text-xs leading-snug text-muted-foreground"
                    >
                      {t(`policies.${value}.description`)}
                    </span>
                  </span>
                </Label>
              ))}
            </RadioGroup>
          </div>
          <div className="grid gap-2 sm:max-w-xs">
            <Label htmlFor={`${ids}-cap`}>{t("cap")}</Label>
            <Input
              id={`${ids}-cap`}
              name="cap"
              type="number"
              inputMode="decimal"
              min={0}
              max={1000}
              step="0.01"
              placeholder={t("capPlaceholder")}
              aria-describedby={`${ids}-cap-hint`}
            />
            <p id={`${ids}-cap-hint`} className="text-xs text-muted-foreground">
              {t("capHint")}
            </p>
          </div>
          <div>
            <Button type="submit" disabled={create.isPending}>
              <PlayIcon aria-hidden />
              {create.isPending ? t("starting") : t("submit")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
