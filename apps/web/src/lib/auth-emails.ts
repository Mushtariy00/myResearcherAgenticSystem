// The email and common namespaces live in the core area (see src/i18n/messages.ts).
import en from "../../messages/en/core.json" with { type: "json" };
import ko from "../../messages/ko/core.json" with { type: "json" };
import { sendMail } from "./mailer.ts";
import type { SetPasswordPurpose } from "./reset-link.ts";

type EmailCopy = { subject: string; body: string };

function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
}

/** One message in both UI languages: lab members may read either. */
export function setPasswordEmail(
  purpose: SetPasswordPurpose,
  data: { name: string; url: string; hours: number },
): { subject: string; text: string } {
  const pick = (copy: { invite: EmailCopy; reset: EmailCopy }) =>
    purpose === "invite" ? copy.invite : copy.reset;
  const english = pick(en.email);
  const korean = pick(ko.email);
  const values = { name: data.name, url: data.url, hours: String(data.hours) };
  const enValues = { ...values, appName: en.common.appName };
  const koValues = { ...values, appName: ko.common.appName };
  return {
    subject: `${fill(english.subject, enValues)} / ${fill(korean.subject, koValues)}`,
    text: `${fill(english.body, enValues)}\n\n-----\n\n${fill(korean.body, koValues)}\n`,
  };
}

export function sendSetPasswordEmail(
  purpose: SetPasswordPurpose,
  data: { to: string; name: string; url: string; hours: number },
): Promise<boolean> {
  return sendMail({ to: data.to, ...setPasswordEmail(purpose, data) });
}
