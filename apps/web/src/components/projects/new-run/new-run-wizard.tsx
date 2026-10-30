"use client";

import {
  AlertCircleIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CircleAlertIcon,
  PlayIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useNewRunForm } from "@/hooks/use-new-run-form";
import { firstStepWithError, NEW_RUN_STEPS, type NewRunStepId } from "@/lib/new-run-schema";
import { cn } from "@/lib/utils";
import { projectHref } from "../project-tabs";
import { EstimatePanel } from "./estimate-panel";
import { ReviewStep } from "./review-step";
import { BudgetStep, LiteratureStep, StagesStep, TopicStep } from "./wizard-steps";

/** The hook's steps, then a review of everything with the full estimate before starting. */
export type WizardStepId = NewRunStepId | "review";

export const WIZARD_STEPS: readonly WizardStepId[] = [
  ...NEW_RUN_STEPS.map((step) => step.id),
  "review",
];

const LAST_FORM_STEP = NEW_RUN_STEPS[NEW_RUN_STEPS.length - 1]?.id ?? "budget";

export type NewRunWizardProps = {
  projectId: string;
  /** False when the project forbids free models (then only Auto is offered). */
  allowFreeModels: boolean;
  /** Test seam: debounce of the live estimate. */
  estimateDebounceMs?: number;
};

/**
 * The new-run wizard: topic, literature options, stages and dataset, models and budget, then a
 * review with the live cost estimate. Each step is checked before the next one; going back keeps
 * every value; Enter moves on. Starting the run opens its page.
 */
export function NewRunWizard({
  projectId,
  allowFreeModels,
  estimateDebounceMs,
}: NewRunWizardProps) {
  const t = useTranslations("wizard");
  const errorMessage = useErrorMessage();
  const router = useRouter();
  const wizard = useNewRunForm(projectId, {
    estimateDebounceMs,
    onCreated: (run) => {
      toast.success(t("started"));
      router.push(`/runs/${run.id}`);
    },
  });
  const { form } = wizard;
  const [reviewing, setReviewing] = useState(false);
  const current: WizardStepId = reviewing ? "review" : wizard.step.id;
  const currentIndex = WIZARD_STEPS.indexOf(current);
  const heading = useRef<HTMLHeadingElement>(null);
  const shown = useRef(current);

  // A new step starts at its heading for keyboard and screen-reader users (not on first load).
  useEffect(() => {
    if (shown.current !== current) {
      shown.current = current;
      heading.current?.focus();
    }
  }, [current]);

  const hasFieldErrors = () =>
    firstStepWithError((path) => Boolean(form.getFieldState(path).error)) >= 0;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reviewing) {
      await wizard.submit();
      // Refused values: the hook went to the step that has them.
      if (hasFieldErrors()) {
        setReviewing(false);
      }
      return;
    }
    // On the last form step this only validates it.
    const valid = await wizard.next();
    if (valid && wizard.isLastStep) {
      setReviewing(true);
    }
  }

  function back() {
    if (reviewing) {
      setReviewing(false);
      return;
    }
    wizard.back();
  }

  async function goTo(id: WizardStepId) {
    if (id !== "review") {
      setReviewing(false);
      await wizard.goTo(id);
      return;
    }
    if (reviewing) {
      return;
    }
    if (await form.trigger(undefined, { shouldFocus: true })) {
      await wizard.goTo(LAST_FORM_STEP);
      setReviewing(true);
      return;
    }
    const failing =
      NEW_RUN_STEPS[firstStepWithError((path) => Boolean(form.getFieldState(path).error))]?.id;
    if (failing) {
      await wizard.goTo(failing);
    }
  }

  const busy = wizard.isSubmitting;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
      <Card className="min-w-0">
        <CardContent className="grid gap-6">
          <nav aria-label={t("stepper.label")}>
            <ol className="grid grid-cols-5 gap-1.5">
              {WIZARD_STEPS.map((id, index) => {
                const state =
                  index === currentIndex ? "current" : index < currentIndex ? "done" : "upcoming";
                const hasError = id !== "review" && wizard.stepErrors[id];
                return (
                  <li key={id} className="min-w-0">
                    <button
                      type="button"
                      onClick={() => void goTo(id)}
                      disabled={busy}
                      aria-current={state === "current" ? "step" : undefined}
                      className={cn(
                        "group grid w-full justify-items-center gap-1.5 rounded-md px-1 py-1.5 text-center text-xs outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60 sm:justify-items-start sm:text-left",
                        state === "current" ? "text-foreground" : "text-muted-foreground",
                      )}
                    >
                      <span
                        aria-hidden
                        className={cn(
                          "h-1 w-full rounded-full",
                          hasError
                            ? "bg-destructive"
                            : state === "upcoming"
                              ? "bg-muted"
                              : "bg-primary",
                        )}
                      />
                      <span className="flex min-w-0 items-center gap-1 font-medium">
                        {hasError ? (
                          <CircleAlertIcon
                            aria-hidden
                            className="size-3.5 shrink-0 text-destructive"
                          />
                        ) : state === "done" ? (
                          <CheckIcon aria-hidden className="size-3.5 shrink-0" />
                        ) : (
                          <span aria-hidden className="tabular-nums">
                            {index + 1}.
                          </span>
                        )}
                        <span aria-hidden className="hidden truncate sm:inline">
                          {t(`steps.${id}.title`)}
                        </span>
                      </span>
                      {/* One name for every width: "Step 2 of 5: Literature, done". */}
                      <span className="sr-only">
                        {t("stepper.stepName", {
                          current: index + 1,
                          total: WIZARD_STEPS.length,
                          name: t(`steps.${id}.title`),
                        })}
                        {hasError
                          ? `, ${t("stepper.hasError")}`
                          : state === "done"
                            ? `, ${t("stepper.done")}`
                            : ""}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>

          <form onSubmit={onSubmit} noValidate className="grid gap-6">
            <div className="grid gap-1">
              <p className="text-xs text-muted-foreground">
                {t("stepper.step", { current: currentIndex + 1, total: WIZARD_STEPS.length })}
              </p>
              <h2 ref={heading} tabIndex={-1} className="text-lg font-semibold outline-none">
                {t(`steps.${current}.title`)}
              </h2>
              <p className="text-sm text-muted-foreground">{t(`steps.${current}.description`)}</p>
            </div>

            {current === "topic" && <TopicStep form={form} />}
            {current === "literature" && <LiteratureStep form={form} />}
            {current === "stages" && <StagesStep form={form} setLastStage={wizard.setLastStage} />}
            {current === "budget" && <BudgetStep form={form} allowFreeModels={allowFreeModels} />}
            {current === "review" && (
              <div className="grid gap-6">
                <ReviewStep form={form} onEdit={(step) => void goTo(step)} />
                <div className="rounded-lg border bg-muted/30 p-4">
                  <EstimatePanel estimate={wizard.estimate} detailed />
                </div>
              </div>
            )}

            {wizard.submitError && (
              <Alert variant="destructive">
                <AlertCircleIcon aria-hidden />
                <AlertDescription>{errorMessage(wizard.submitError)}</AlertDescription>
              </Alert>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={back}
                  disabled={currentIndex === 0 || busy}
                >
                  <ChevronLeftIcon aria-hidden />
                  {t("back")}
                </Button>
                <Link
                  href={projectHref(projectId)}
                  className={buttonVariants({ variant: "ghost" })}
                >
                  {t("cancel")}
                </Link>
              </div>
              <Button type="submit" disabled={busy}>
                {current === "review" ? (
                  <>
                    <PlayIcon aria-hidden />
                    {busy ? t("starting") : t("start")}
                  </>
                ) : (
                  <>
                    {current === LAST_FORM_STEP ? t("toReview") : t("next")}
                    <ChevronRightIcon aria-hidden />
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {current !== "review" && (
        <aside aria-label={t("estimate.title")} className="lg:sticky lg:top-20">
          <Card size="sm">
            <CardContent>
              <EstimatePanel estimate={wizard.estimate} />
            </CardContent>
          </Card>
        </aside>
      )}
    </div>
  );
}
