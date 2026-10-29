"use client";

import { CheckIcon, CopyIcon, MailIcon, MailXIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SET_PASSWORD_LINK_HOURS } from "@/lib/password-policy";

export type IssuedLink = { email: string; url: string; emailed: boolean; kind: "invite" | "reset" };

/** Shows a set-password link once, so invites work even without email. */
export function LinkDialog({ link, onClose }: { link: IssuedLink | null; onClose: () => void }) {
  const t = useTranslations("admin.link");
  const id = useId();
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!link) {
      return;
    }
    try {
      await navigator.clipboard.writeText(link.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      document.getElementById(id)?.focus();
      (document.getElementById(id) as HTMLInputElement | null)?.select();
    }
  }

  return (
    <Dialog
      open={link !== null}
      onOpenChange={(open) => {
        if (!open) {
          setCopied(false);
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{link?.kind === "invite" ? t("inviteTitle") : t("resetTitle")}</DialogTitle>
          <DialogDescription>
            {t("description", { email: link?.email ?? "", hours: SET_PASSWORD_LINK_HOURS })}
          </DialogDescription>
        </DialogHeader>
        {link && (
          <div className="grid gap-4">
            <Alert>
              {link.emailed ? <MailIcon aria-hidden /> : <MailXIcon aria-hidden />}
              <AlertDescription>
                {link.emailed ? t("emailed", { email: link.email }) : t("notEmailed")}
              </AlertDescription>
            </Alert>
            <div className="grid gap-2">
              <Label htmlFor={id}>{t("label")}</Label>
              <div className="flex gap-2">
                <Input
                  id={id}
                  readOnly
                  value={link.url}
                  className="font-mono text-xs"
                  onFocus={(event) => event.currentTarget.select()}
                />
                <Button type="button" variant="outline" onClick={copy} aria-live="polite">
                  {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
                  {copied ? t("copied") : t("copy")}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">{t("warning")}</p>
            </div>
          </div>
        )}
        <DialogFooter showCloseButton />
      </DialogContent>
    </Dialog>
  );
}
