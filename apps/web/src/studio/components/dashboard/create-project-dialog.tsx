"use client";

import { Dialog } from "@base-ui/react/dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PlusIcon, XIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { toast } from "sonner";
import { createProjectMutation, listProjectsQueryKey } from "@/client/@tanstack/react-query.gen";
import { cn } from "@/lib/utils";
import { ShimmerButton } from "@/studio/components/effects/shimmer-button";
import { studioProjectPath } from "@/studio/lib/nav";
import { GHOST_BUTTON, ICON_BUTTON } from "@/studio/lib/ui";
import { STUDIO_FIELD, STUDIO_LABEL } from "./studio-fields";
import { StudioInlineError } from "./studio-panel";

export const STUDIO_BACKDROP =
  "fixed inset-0 z-50 bg-[oklch(0.1_0.02_265/0.5)] transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

export const STUDIO_DIALOG =
  "studio-glass studio-blur fixed top-1/2 left-1/2 z-50 max-h-[calc(100dvh-2rem)] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto overscroll-contain rounded-2xl bg-(--studio-glass-strong) p-5 text-foreground outline-none sm:p-6 transition-[scale,opacity] duration-200 ease-out data-ending-style:scale-[0.98] data-ending-style:opacity-0 data-starting-style:scale-[0.98] data-starting-style:opacity-0 motion-reduce:transition-none";

/**
 * "New project" as a Studio glass dialog: the same request as Classic (you become the owner),
 * then the new project's Studio page.
 */
export function CreateProjectDialog() {
  const t = useTranslations("dashboard.create");
  const tWork = useTranslations("studioWork.dashboard");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const queryClient = useQueryClient();
  const ids = useId();
  const [open, setOpen] = useState(false);
  const create = useMutation({
    ...createProjectMutation(),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: listProjectsQueryKey() });
      toast.success(t("created", { name: project.name }));
      setOpen(false);
      router.push(studioProjectPath(project.id));
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      body: {
        name: String(form.get("name") ?? "").trim(),
        description: String(form.get("description") ?? "").trim(),
      },
    });
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          create.reset();
        }
      }}
    >
      <Dialog.Trigger render={<ShimmerButton size="sm" />}>
        <PlusIcon aria-hidden />
        {t("open")}
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className={STUDIO_BACKDROP} />
        <Dialog.Popup className={STUDIO_DIALOG}>
          <form onSubmit={onSubmit} className="grid gap-5">
            <div className="flex items-start justify-between gap-3">
              <div className="grid gap-1">
                <Dialog.Title className="studio-display text-xl text-foreground">
                  {t("title")}
                </Dialog.Title>
                <Dialog.Description className="text-sm text-muted-foreground">
                  {t("description")}
                </Dialog.Description>
              </div>
              <Dialog.Close
                aria-label={tCommon("close")}
                className={cn(ICON_BUTTON, "-mt-1 -mr-2")}
              >
                <XIcon aria-hidden />
              </Dialog.Close>
            </div>
            {create.isError && (
              <StudioInlineError error={create.error} title={tWork("createFailed")} />
            )}
            <div className="grid gap-2">
              <label htmlFor={`${ids}-name`} className={STUDIO_LABEL}>
                {t("name")}
              </label>
              <input
                id={`${ids}-name`}
                name="name"
                required
                maxLength={200}
                autoComplete="off"
                className={STUDIO_FIELD}
              />
            </div>
            <div className="grid gap-2">
              <label htmlFor={`${ids}-description`} className={STUDIO_LABEL}>
                {t("descriptionLabel")}
              </label>
              <textarea
                id={`${ids}-description`}
                name="description"
                maxLength={5000}
                rows={3}
                placeholder={t("descriptionPlaceholder")}
                className={cn(STUDIO_FIELD, "h-auto min-h-20 py-2")}
              />
            </div>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Dialog.Close className={cn(GHOST_BUTTON, "h-10 justify-center")}>
                {tCommon("cancel")}
              </Dialog.Close>
              <ShimmerButton type="submit" disabled={create.isPending}>
                {create.isPending ? tCommon("creating") : t("submit")}
              </ShimmerButton>
            </div>
          </form>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
