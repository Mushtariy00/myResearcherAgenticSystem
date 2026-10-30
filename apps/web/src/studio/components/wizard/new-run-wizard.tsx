"use client";

import { Dialog } from "@base-ui/react/dialog";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  CircleAlertIcon,
  PlayIcon,
  XIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useCallback, useRef, useState } from "react";
import { toast } from "sonner";
import { type NewRunForm, useNewRunForm } from "@/hooks/use-new-run-form";
import type { NewRunStepId } from "@/lib/new-run-schema";
import { cn } from "@/lib/utils";
import { STUDIO_BACKDROP } from "@/studio/components/dashboard/create-project-dialog";
import { StudioInlineError } from "@/studio/components/dashboard/studio-panel";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { EASE_OUT } from "@/studio/lib/motion";
import { studioRunPath } from "@/studio/lib/nav";
import { GHOST_BUTTON, ICON_BUTTON, OUTLINE_BUTTON } from "@/studio/lib/ui";
import { CostEstimate } from "./cost-estimate";
import { BudgetStep, LiteratureStep, StagesStep, TopicStep } from "./wizard-steps";

const STEP_VARIANTS = {
  enter: (direction: number) => ({ x: direction * 28, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (direction: number) => ({ x: direction * -28, opacity: 0 }),
};

function StepBody({
  step,
  wizard,
  allowFreeModels,
}: {
  step: NewRunStepId;
  wizard: NewRunForm;
  allowFreeModels: boolean;
}) {
  switch (step) {
    case "topic":
      return <TopicStep wizard={wizard} />;
    case "literature":
      return <LiteratureStep wizard={wizard} />;
    case "stages":
      return <StagesStep wizard={wizard} />;
    case "budget":
      return <BudgetStep wizard={wizard} allowFreeModels={allowFreeModels} />;
  }
}

export type NewRunWizardProps = {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The project allows free models (Free only is offered). */
  allowFreeModels?: boolean;
};

/**
 * The new-run wizard as a multi-step glass dialog over the shared form (useNewRunForm): topic,
 * literature, stages and dataset, then models and budget, with the live cost estimate beside
 * every step. Steps slide in the direction of travel (a plain fade with reduced motion), focus
 * moves to each new step's heading, and the stepper jumps back at once or forward past valid
 * steps. Values survive closing the dialog; a created run opens its Studio page.
 */
export function NewRunWizard({
  projectId,
  open,
  onOpenChange,
  allowFreeModels = true,
}: NewRunWizardProps) {
  const t = useTranslations("studioWork.wizard");
  const tRun = useTranslations("project.newRun");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const wizard = useNewRunForm(projectId, {
    onCreated: (run) => {
      toast.success(tRun("started"));
      onOpenChange(false);
      router.push(studioRunPath(run.id));
    },
  });
  const { step, stepIndex, steps, stepErrors, isFirstStep, isLastStep, isSubmitting } = wizard;

  // The direction of travel, for the slide (derived from the step index as it changes).
  const [travel, setTravel] = useState({ index: stepIndex, direction: 1 });
  if (travel.index !== stepIndex) {
    setTravel({ index: stepIndex, direction: stepIndex > travel.index ? 1 : -1 });
  }

  // A new step's heading takes focus once it has slid in, so keyboard and screen reader users
  // land on it; failed validation leaves focus on the first invalid field instead.
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const focusNextHeading = useRef(false);
  const setHeading = useCallback((node: HTMLHeadingElement | null) => {
    headingRef.current = node;
    if (node && focusNextHeading.current) {
      focusNextHeading.current = false;
      node.focus();
    }
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    focusNextHeading.current = true;
    await wizard.onSubmit(event);
  }

  async function goTo(id: NewRunStepId) {
    if (id === step.id) {
      return;
    }
    focusNextHeading.current = true;
    await wizard.goTo(id);
  }

  function back() {
    focusNextHeading.current = true;
    wizard.back();
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className={STUDIO_BACKDROP} />
        <Dialog.Popup
          initialFocus={headingRef}
          className={cn(
            "studio-glass studio-blur fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100dvh-1rem)] w-[min(60rem,calc(100vw-1rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl bg-(--studio-glass-strong) text-foreground outline-none sm:max-h-[calc(100dvh-2rem)]",
            "transition-[scale,opacity] duration-200 ease-out data-ending-style:scale-[0.98] data-ending-style:opacity-0 data-starting-style:scale-[0.98] data-starting-style:opacity-0 motion-reduce:transition-none",
          )}
        >
          <div className="flex items-start justify-between gap-3 px-4 pt-4 sm:px-6 sm:pt-6">
            <div className="grid min-w-0 gap-1">
              <Dialog.Title className="studio-display text-xl text-foreground sm:text-2xl">
                {tRun("title")}
              </Dialog.Title>
              <Dialog.Description className="text-sm text-pretty text-muted-foreground">
                {tRun("description")}
              </Dialog.Description>
            </div>
            <Dialog.Close aria-label={tCommon("close")} className={cn(ICON_BUTTON, "-mt-1 -mr-2")}>
              <XIcon aria-hidden />
            </Dialog.Close>
          </div>

          <nav aria-label={t("steps")} className="px-4 pt-4 sm:px-6">
            <ol className="flex gap-1 overflow-x-auto p-1 sm:gap-2">
              {steps.map((item, index) => {
                const current = index === stepIndex;
                const done = index < stepIndex;
                const failed = stepErrors[item.id];
                return (
                  <li key={item.id} className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => void goTo(item.id)}
                      aria-current={current ? "step" : undefined}
                      disabled={isSubmitting}
                      className={cn(
                        "flex w-full min-w-0 items-center gap-2 rounded-xl px-2 py-2 text-left text-xs font-medium outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 sm:px-3 sm:text-sm",
                        current
                          ? "bg-(--studio-glass-strong) text-foreground shadow-[inset_0_0_0_1px_var(--studio-glass-border)]"
                          : "text-muted-foreground hover:bg-(--studio-hover) hover:text-foreground",
                      )}
                    >
                      <span
                        aria-hidden
                        data-tone={
                          failed ? "danger" : done ? "success" : current ? "info" : "neutral"
                        }
                        className="flex size-6 shrink-0 items-center justify-center rounded-full border border-(--tone)/40 bg-(--tone)/14 font-mono text-[0.7rem] text-(--tone-fg) tabular-nums"
                      >
                        {failed ? (
                          <CircleAlertIcon className="size-3.5" />
                        ) : done ? (
                          <CheckIcon className="size-3.5" />
                        ) : (
                          index + 1
                        )}
                      </span>
                      <span className="hidden truncate min-[480px]:inline">
                        {t(`stepTitles.${item.id}`)}
                      </span>
                      <span className="sr-only min-[480px]:hidden">
                        {t(`stepTitles.${item.id}`)}
                      </span>
                      {failed && <span className="sr-only">{t("stepHasErrors")}</span>}
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>

          <form
            noValidate
            onSubmit={onSubmit}
            aria-busy={isSubmitting || undefined}
            className="flex min-h-0 flex-1 flex-col"
          >
            <div className="grid min-h-0 flex-1 gap-5 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
              <div className="min-w-0 overflow-x-clip">
                <AnimatePresence mode="wait" initial={false} custom={travel.direction}>
                  <motion.div
                    key={step.id}
                    custom={travel.direction}
                    variants={STEP_VARIANTS}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.22, ease: EASE_OUT }}
                    className="grid gap-5"
                  >
                    <div className="grid gap-1">
                      <h3
                        ref={setHeading}
                        tabIndex={-1}
                        className="text-lg font-semibold tracking-tight text-foreground outline-none focus-visible:ring-3 focus-visible:ring-ring/50 rounded-md"
                      >
                        <span className="sr-only">
                          {t("stepOf", { step: stepIndex + 1, total: steps.length })}
                        </span>{" "}
                        {t(`stepTitles.${step.id}`)}
                      </h3>
                      <p className="text-sm text-pretty text-muted-foreground">
                        {t(`stepDescriptions.${step.id}`)}
                      </p>
                    </div>
                    <StepBody step={step.id} wizard={wizard} allowFreeModels={allowFreeModels} />
                  </motion.div>
                </AnimatePresence>
              </div>
              <CostEstimate estimate={wizard.estimate} className="lg:sticky lg:top-0" />
            </div>

            <div className="grid gap-3 border-t border-(--studio-glass-border) px-4 py-3 sm:px-6 sm:py-4">
              {wizard.submitError && (
                <StudioInlineError error={wizard.submitError} title={t("submitFailed")} />
              )}
              <div className="flex flex-wrap items-center justify-between gap-2">
                {isFirstStep ? (
                  <Dialog.Close className={cn(GHOST_BUTTON, "h-10")}>
                    {tCommon("cancel")}
                  </Dialog.Close>
                ) : (
                  <button
                    type="button"
                    onClick={back}
                    disabled={isSubmitting}
                    className={cn(OUTLINE_BUTTON, "disabled:opacity-60")}
                  >
                    <ArrowLeftIcon aria-hidden />
                    {t("back")}
                  </button>
                )}
                <p
                  aria-hidden
                  className="order-last w-full text-center text-xs text-muted-foreground tabular-nums sm:order-none sm:w-auto"
                >
                  {t("stepOf", { step: stepIndex + 1, total: steps.length })}
                </p>
                {isLastStep ? (
                  <ShimmerButton type="submit" disabled={isSubmitting}>
                    <PlayIcon aria-hidden />
                    {isSubmitting ? tRun("starting") : tRun("submit")}
                  </ShimmerButton>
                ) : (
                  <ShimmerButton type="submit" disabled={isSubmitting}>
                    {t("next")}
                    <ArrowRightIcon aria-hidden />
                  </ShimmerButton>
                )}
              </div>
            </div>
          </form>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
