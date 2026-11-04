"use client";

import { useTranslations } from "next-intl";
import type { ReviewAttempt } from "@/hooks/use-approval-decision";

/**
 * Which attempt an output under review is, in both interfaces. After a retry it carries the
 * stage's own number too, the one its timeline and versions show.
 */
export function AttemptLabel({ attempt }: { attempt: ReviewAttempt }) {
  const t = useTranslations("run.approval");
  if (attempt.of === null) {
    return <>{t("attempt", { attempt: attempt.number })}</>;
  }
  if (attempt.stageAttempt !== null) {
    return (
      <>
        {t("attemptOfAfterRetry", {
          attempt: attempt.stageAttempt,
          number: attempt.number,
          max: attempt.of,
        })}
      </>
    );
  }
  return <>{t("attemptOf", { attempt: attempt.number, max: attempt.of })}</>;
}
