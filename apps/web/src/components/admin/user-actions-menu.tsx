"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  KeyRoundIcon,
  LogOutIcon,
  MoreHorizontalIcon,
  UserCheckIcon,
  UserXIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState, useTransition } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  type OffboardingResult,
  restoreUser,
  signOutEverywhere,
  suspendUser,
} from "@/lib/admin-offboarding";
import { authErrorKey } from "@/lib/auth-client";
import { cn } from "@/lib/utils";
import { ADMIN_USERS_QUERY_KEY, displayName, type LabUser } from "./use-lab-users";

export type OffboardingAction = "suspend" | "restore" | "signOut";

/** Codes the offboarding actions return beyond the shared `auth.errors.*` ones. */
const OFFBOARDING_ERROR_CODES = [
  "OWN_ACCOUNT",
  "YOU_CANNOT_BAN_YOURSELF",
  "YOU_ARE_NOT_ALLOWED_TO_BAN_USERS",
  "YOU_ARE_NOT_ALLOWED_TO_REVOKE_USERS_SESSIONS",
] as const;

type OffboardingErrorCode = (typeof OFFBOARDING_ERROR_CODES)[number];

function isOffboardingErrorCode(code: string): code is OffboardingErrorCode {
  return (OFFBOARDING_ERROR_CODES as readonly string[]).includes(code);
}

const RUN: Record<OffboardingAction, (input: { userId: string }) => Promise<OffboardingResult>> = {
  suspend: suspendUser,
  restore: restoreUser,
  signOut: signOutEverywhere,
};

const DONE = { suspend: "suspended", restore: "restored", signOut: "signedOut" } as const;

/** The translated reason an offboarding action failed. */
export function useOffboardingErrorText(): (code: string) => string {
  const t = useTranslations("admin.offboarding.errors");
  const te = useTranslations("auth.errors");
  return (code) => (isOffboardingErrorCode(code) ? t(code) : te(authErrorKey({ code })));
}

export type UserActionsMenuProps = {
  user: LabUser;
  /** The signed-in admin: they cannot suspend or sign out their own account here. */
  isSelf: boolean;
  /** Issues a new set-password link (see LinkDialog); disabled while one is on its way. */
  onPasswordLink: (user: LabUser) => void;
  passwordLinkPending?: boolean;
  /** Restyles the "⋯" trigger (Studio). */
  triggerClassName?: string;
};

/**
 * Row actions for one account, in both interfaces: a new password link, and offboarding
 * (suspend or restore access, sign out everywhere). Offboarding always asks for confirmation
 * first; the dialog stays open with the reason when the action fails.
 */
export function UserActionsMenu({
  user,
  isSelf,
  onPasswordLink,
  passwordLinkPending = false,
  triggerClassName,
}: UserActionsMenuProps) {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const errorText = useOffboardingErrorText();
  const queryClient = useQueryClient();
  const trigger = useRef<HTMLButtonElement>(null);
  // The action stays set while the dialog closes, so its text does not vanish mid-animation.
  const [action, setAction] = useState<OffboardingAction>("suspend");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const name = displayName(user);
  const banned = user.banned === true;

  function ask(next: OffboardingAction) {
    setError(null);
    setAction(next);
    setOpen(true);
  }

  function confirm() {
    const current = action;
    setError(null);
    startTransition(async () => {
      const result = await RUN[current]({ userId: user.id });
      if (!result.ok) {
        setError(errorText(result.code));
        return;
      }
      setOpen(false);
      toast.success(t(`offboarding.${DONE[current]}`, { name }));
      await queryClient.invalidateQueries({ queryKey: ADMIN_USERS_QUERY_KEY });
    });
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          ref={trigger}
          render={
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t("users.actionsFor", { name })}
              className={cn(triggerClassName)}
            >
              <MoreHorizontalIcon aria-hidden />
            </Button>
          }
        />
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuGroup>
            <DropdownMenuItem disabled={passwordLinkPending} onClick={() => onPasswordLink(user)}>
              <KeyRoundIcon aria-hidden />
              {t("users.newLink")}
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem disabled={isSelf || banned} onClick={() => ask("signOut")}>
              <LogOutIcon aria-hidden />
              {t("offboarding.signOut")}
            </DropdownMenuItem>
            {banned ? (
              <DropdownMenuItem onClick={() => ask("restore")}>
                <UserCheckIcon aria-hidden />
                {t("offboarding.restore")}
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem
                variant="destructive"
                disabled={isSelf}
                onClick={() => ask("suspend")}
              >
                <UserXIcon aria-hidden />
                {t("offboarding.suspend")}
              </DropdownMenuItem>
            )}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          // Not while the action runs: its outcome must stay visible.
          if (!next && !pending) {
            setOpen(false);
          }
        }}
      >
        <AlertDialogContent finalFocus={trigger}>
          <AlertDialogHeader>
            <AlertDialogTitle>{t(`offboarding.${action}Title`, { name })}</AlertDialogTitle>
            <AlertDialogDescription>
              {t(`offboarding.${action}Description`, { email: user.email })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {error && (
            <Alert variant="destructive">
              <AlertCircleIcon aria-hidden />
              <AlertTitle>{t("offboarding.failed")}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>{tCommon("cancel")}</AlertDialogCancel>
            <Button
              variant={action === "restore" ? "default" : "destructive"}
              disabled={pending}
              onClick={confirm}
            >
              {pending ? t("offboarding.working") : t(`offboarding.${action}Confirm`)}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
