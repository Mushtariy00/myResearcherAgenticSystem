"use client";

import {
  ArrowDownIcon,
  ArrowUpIcon,
  CircleAlertIcon,
  PencilIcon,
  PlusIcon,
  XIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import type { ModelRoutingOut, RoleRoutingOut, RoutedModelOut } from "@/client";
import { QueryError } from "@/components/app/query-state";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useErrorMessage } from "@/hooks/use-error-message";
import { useModelCatalog, useSetRoleModels } from "@/hooks/use-model-routing";
import { keyedChain, MAX_CHAIN_MODELS, movedOnePlace, pickableModels } from "./admin-format";
import { useAdminLabels, useModelText } from "./admin-labels";

/** How many matches the picker lists: the catalog has hundreds, and typing narrows it. */
const PICKER_ROWS = 30;

function ModelLine({ model }: { model: RoutedModelOut }) {
  const describe = useModelText();
  const { price, context } = describe(model);
  return (
    <span className="grid min-w-0 gap-0.5">
      <span className="truncate font-mono text-xs" title={model.id}>
        {model.id}
      </span>
      <span className="text-xs whitespace-normal text-muted-foreground">
        {context ? `${price} · ${context}` : price}
      </span>
    </span>
  );
}

/** The catalog's models a chain can take, searched by name; choosing one adds it to the end. */
function ModelPicker({
  free,
  chosen,
  onAdd,
}: {
  free: boolean;
  chosen: readonly string[];
  onAdd: (id: string) => void;
}) {
  const t = useTranslations("admin.routing.editor");
  const tCommon = useTranslations("common");
  const catalog = useModelCatalog();
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  if (chosen.length >= MAX_CHAIN_MODELS) {
    return <p className="text-xs text-muted-foreground">{t("full", { max: MAX_CHAIN_MODELS })}</p>;
  }
  if (catalog.isPending) {
    return (
      <div className="grid gap-1.5" aria-busy="true">
        <span className="sr-only">{tCommon("loading")}</span>
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (catalog.isError) {
    return <QueryError error={catalog.error} onRetry={() => catalog.refetch()} />;
  }
  if (catalog.data.checked_at === null) {
    return <p className="text-xs text-muted-foreground">{t("catalogMissing")}</p>;
  }
  const matches = pickableModels(catalog.data.models, { free, chosen, query });
  const shown = matches.slice(0, PICKER_ROWS);
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={inputId} className="text-xs">
        {t("search")}
      </Label>
      <Input
        ref={input}
        id={inputId}
        type="search"
        value={query}
        placeholder={t("searchPlaceholder")}
        onChange={(event) => setQuery(event.target.value)}
      />
      {shown.length > 0 && (
        <ul className="grid max-h-44 gap-0.5 overflow-y-auto rounded-lg border p-1">
          {shown.map((model) => (
            <li key={model.id}>
              <button
                type="button"
                aria-label={t("add", { model: model.id })}
                className="flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1 text-left outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                onClick={() => {
                  onAdd(model.id);
                  // The button goes with the model: the next choice starts from the search box.
                  input.current?.focus();
                }}
              >
                <PlusIcon aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
                <ModelLine model={model} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p aria-live="polite" className="text-xs text-muted-foreground">
        {shown.length === 0
          ? t("noMatches")
          : matches.length > shown.length
            ? t("moreMatches", { shown: shown.length, total: matches.length })
            : null}
      </p>
    </div>
  );
}

/** One chain of a role: the lab's, read-only, or the role's own to order, trim and add to. */
function ChainEditor({
  free,
  title,
  hint,
  lab,
  current,
  known,
  draft,
  onChange,
}: {
  free: boolean;
  title: string;
  hint: string;
  /** The lab's chain, which the role follows while `draft` is null. */
  lab: RoutedModelOut[];
  /** What the role tries today: where its own list starts from. */
  current: RoutedModelOut[];
  known: ReadonlyMap<string, RoutedModelOut>;
  draft: string[] | null;
  onChange: (draft: string[] | null) => void;
}) {
  const t = useTranslations("admin.routing.editor");
  const ids = useId();
  const section = useRef<HTMLElement>(null);
  const focusAfterMove = useRef<{ id: string; first: string; second: string } | null>(null);

  // Moving a row can take its button out of focus (React moves the DOM node), so the focus goes
  // back on it, or on the other arrow once the row reaches the end of the list.
  useEffect(() => {
    const target = focusAfterMove.current;
    focusAfterMove.current = null;
    if (!target || !section.current) {
      return;
    }
    const buttons = [...section.current.querySelectorAll<HTMLButtonElement>("[data-move]")].filter(
      (button) => button.dataset.model === target.id && !button.disabled,
    );
    const next =
      buttons.find((button) => button.dataset.move === target.first) ??
      buttons.find((button) => button.dataset.move === target.second);
    next?.focus();
  });

  const move = (index: number, id: string, by: -1 | 1) => {
    if (draft) {
      focusAfterMove.current =
        by < 0 ? { id, first: "up", second: "down" } : { id, first: "down", second: "up" };
      onChange(movedOnePlace(draft, index, by));
    }
  };

  return (
    <section
      ref={section}
      tabIndex={-1}
      aria-labelledby={`${ids}-title`}
      className="grid min-w-0 content-start gap-3 outline-none"
    >
      <div className="grid gap-0.5">
        <h3 id={`${ids}-title`} className="text-sm font-medium">
          {title}
        </h3>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <div className="flex items-center gap-2">
        <Switch
          aria-labelledby={`${ids}-title ${ids}-lab`}
          checked={draft === null}
          onCheckedChange={(useLab) =>
            onChange(
              useLab
                ? null
                : [...new Set(current.map((model) => model.id))].slice(0, MAX_CHAIN_MODELS),
            )
          }
        />
        <span id={`${ids}-lab`} className="text-sm">
          {t("useLab")}
        </span>
      </div>
      {draft === null ? (
        <ol className="grid gap-2 rounded-lg border border-dashed p-2">
          {keyedChain(lab).map(({ key, model }) => (
            <li key={key} className="min-w-0">
              <ModelLine model={model} />
            </li>
          ))}
        </ol>
      ) : (
        <>
          {draft.length === 0 ? (
            <p className="rounded-lg border border-dashed p-2 text-xs text-muted-foreground">
              {free ? t("freeNeeded") : t("noPaid")}
            </p>
          ) : (
            <ol className="grid gap-1 rounded-lg border p-1">
              {draft.map((id, index) => (
                <li key={id} className="flex min-w-0 items-center gap-1 px-1 py-0.5">
                  <span aria-hidden className="text-xs text-muted-foreground tabular-nums">
                    {index + 1}.
                  </span>
                  <span className="min-w-0 flex-1">
                    <ModelLine
                      model={
                        known.get(id) ?? {
                          id,
                          free,
                          in_catalog: false,
                          context_length: null,
                          prompt_usd_per_mtok: null,
                          completion_usd_per_mtok: null,
                        }
                      }
                    />
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("moveUp", { model: id })}
                    data-move="up"
                    data-model={id}
                    disabled={index === 0}
                    onClick={() => move(index, id, -1)}
                  >
                    <ArrowUpIcon aria-hidden />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("moveDown", { model: id })}
                    data-move="down"
                    data-model={id}
                    disabled={index === draft.length - 1}
                    onClick={() => move(index, id, 1)}
                  >
                    <ArrowDownIcon aria-hidden />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("remove", { model: id })}
                    onClick={() => {
                      onChange(draft.filter((other) => other !== id));
                      // The button goes with the row: keep the place in this list.
                      section.current?.focus();
                    }}
                  >
                    <XIcon aria-hidden />
                  </Button>
                </li>
              ))}
            </ol>
          )}
          <ModelPicker
            free={free}
            chosen={draft}
            onAdd={(id) => {
              onChange([...draft, id]);
              if (draft.length + 1 >= MAX_CHAIN_MODELS) {
                section.current?.focus(); // The picker gives way to "the list is full".
              }
            }}
          />
        </>
      )}
    </section>
  );
}

function saved(chain: RoutedModelOut[], isLabDefault: boolean): string[] | null {
  return isLabDefault ? null : chain.map((model) => model.id);
}

/** Mounted while the dialog is open, so every opening starts from what is saved. */
function RoleModelsForm({
  role,
  routing,
  roleName,
  onDone,
}: {
  role: RoleRoutingOut;
  routing: ModelRoutingOut;
  roleName: string;
  onDone: () => void;
}) {
  const t = useTranslations("admin.routing");
  const tCommon = useTranslations("common");
  const errorMessage = useErrorMessage();
  const save = useSetRoleModels();
  const catalog = useModelCatalog();
  const savedPaid = saved(role.paid, role.paid_is_lab_default);
  const savedFree = saved(role.free, role.free_is_lab_default);
  const [paid, setPaid] = useState(savedPaid);
  const [free, setFree] = useState(savedFree);

  const known = useMemo(
    () =>
      new Map(
        [
          ...routing.lab_paid,
          ...routing.lab_free,
          ...role.paid,
          ...role.free,
          ...(catalog.data?.models ?? []),
        ].map((model) => [model.id, model]),
      ),
    [routing, role, catalog.data],
  );

  const unchanged = JSON.stringify([paid, free]) === JSON.stringify([savedPaid, savedFree]);
  const freeMissing = free !== null && free.length === 0;

  return (
    <form
      className="grid gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(
          { path: { role: role.role }, body: { paid, free } },
          {
            onSuccess: () => {
              toast.success(t("editor.savedToast", { role: roleName }));
              onDone();
            },
          },
        );
      }}
    >
      <div className="grid gap-6 md:grid-cols-2">
        <ChainEditor
          free={false}
          title={t("paid")}
          hint={t("editor.paidHint")}
          lab={routing.lab_paid}
          current={role.paid}
          known={known}
          draft={paid}
          onChange={setPaid}
        />
        <ChainEditor
          free
          title={t("free")}
          hint={t("editor.freeHint")}
          lab={routing.lab_free}
          current={role.free}
          known={known}
          draft={free}
          onChange={setFree}
        />
      </div>
      {save.error && (
        <Alert variant="destructive">
          <CircleAlertIcon aria-hidden />
          <AlertDescription>{errorMessage(save.error)}</AlertDescription>
        </Alert>
      )}
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" />}>
          {tCommon("cancel")}
        </DialogClose>
        <Button type="submit" disabled={save.isPending || unchanged || freeMissing}>
          {save.isPending ? t("editor.saving") : t("editor.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

/** Choosing an agent role's own models, in both interfaces. */
export function RoleModelsDialog({
  role,
  routing,
}: {
  role: RoleRoutingOut;
  routing: ModelRoutingOut;
}) {
  const t = useTranslations("admin.routing");
  const labels = useAdminLabels();
  const [open, setOpen] = useState(false);
  const roleName = labels.agentRole(role.role);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label={t("editFor", { role: roleName })}
          />
        }
      >
        <PencilIcon aria-hidden />
        {t("edit")}
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("editor.title", { role: roleName })}</DialogTitle>
          <DialogDescription>{t("editor.description")}</DialogDescription>
        </DialogHeader>
        <RoleModelsForm
          role={role}
          routing={routing}
          roleName={roleName}
          onDone={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
