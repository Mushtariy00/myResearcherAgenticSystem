"use client";

import { Dialog } from "@base-ui/react/dialog";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  CornerDownLeftIcon,
  FolderIcon,
  LanguagesIcon,
  LayoutTemplateIcon,
  type LucideIcon,
  MonitorIcon,
  MoonIcon,
  SearchIcon,
  SunIcon,
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { type ReactNode, type Ref, useEffect, useRef } from "react";
import { listProjectsOptions } from "@/client/@tanstack/react-query.gen";
import { useCurrentUser } from "@/components/app/current-user";
import { useChooseLocale } from "@/components/app/use-choose-locale";
import { locales } from "@/i18n/config";
import { toClassicPath } from "@/lib/ui-version";
import { cn } from "@/lib/utils";
import { studioProjectPath, visibleNav } from "@/studio/lib/nav";
import { useNavLabels } from "./studio-nav-list";

const THEMES = [
  { value: "light", icon: SunIcon },
  { value: "dark", icon: MoonIcon },
  { value: "system", icon: MonitorIcon },
] as const;

const GROUP =
  "px-1 pb-1 [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-[0.7rem] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:uppercase";

function PaletteItem({
  value,
  keywords,
  icon: Icon,
  onSelect,
  children,
  hint,
}: {
  value: string;
  keywords?: string[];
  icon: LucideIcon;
  onSelect: () => void;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <Command.Item
      value={value}
      keywords={keywords}
      onSelect={onSelect}
      className="group/item relative flex h-10 cursor-default items-center gap-3 rounded-[10px] px-2.5 text-sm text-foreground outline-none select-none data-[disabled=true]:opacity-50 data-[selected=true]:bg-(--studio-glass-strong) data-[selected=true]:shadow-[inset_0_0_0_1px_var(--studio-glass-border)]"
    >
      <Icon
        aria-hidden
        className="size-4 shrink-0 text-muted-foreground group-data-[selected=true]/item:text-(--studio-accent-fg)"
      />
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {hint}
    </Command.Item>
  );
}

/**
 * The command list inside the palette: go to a page or a project, open the page in Classic, or
 * switch language or theme. Typing filters (cmdk scoring over labels and keywords); arrow keys
 * move, Enter runs the item, and `onDone` closes the palette.
 */
export function CommandPaletteContent({
  onDone,
  inputRef,
}: {
  onDone: () => void;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const t = useTranslations();
  const router = useRouter();
  const pathname = usePathname();
  const { locale, chooseLocale } = useChooseLocale();
  const { theme, setTheme } = useTheme();
  const user = useCurrentUser();
  const navLabels = useNavLabels();
  const projects = useQuery(listProjectsOptions());

  function go(href: string) {
    onDone();
    router.push(href);
  }

  const current = (
    <span className="text-xs text-muted-foreground">
      <CheckIcon aria-hidden className="inline size-3.5" />
      <span className="sr-only">{t("studio.palette.current")}</span>
    </span>
  );

  return (
    <Command
      label={t("studio.palette.title")}
      loop
      className="flex max-h-[min(36rem,calc(100dvh-6rem))] flex-col"
    >
      <div className="flex items-center gap-3 border-b border-(--studio-glass-border) px-4">
        <SearchIcon aria-hidden className="size-4.5 shrink-0 text-muted-foreground" />
        <Command.Input
          ref={inputRef}
          placeholder={t("studio.palette.placeholder")}
          className="h-14 min-w-0 flex-1 bg-transparent text-base text-foreground outline-none placeholder:text-muted-foreground sm:text-sm"
        />
      </div>
      <Command.List className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2 [scroll-padding-block:0.5rem]">
        <Command.Empty className="px-3 py-10 text-center text-sm text-muted-foreground">
          {t("studio.palette.empty")}
        </Command.Empty>

        <Command.Group heading={t("studio.palette.groups.navigate")} className={GROUP}>
          {visibleNav(user.role).map((item) => (
            <PaletteItem
              key={item.id}
              value={`nav ${item.id} ${navLabels[item.id]}`}
              keywords={[item.id]}
              icon={item.icon}
              onSelect={() => go(item.href)}
            >
              {navLabels[item.id]}
            </PaletteItem>
          ))}
        </Command.Group>

        <Command.Group heading={t("studio.palette.groups.projects")} className={GROUP}>
          {projects.isPending && (
            <Command.Loading>
              <p className="px-2.5 py-2 text-sm text-muted-foreground">
                {t("studio.palette.loading")}
              </p>
            </Command.Loading>
          )}
          {projects.data?.map((project) => (
            <PaletteItem
              key={project.id}
              value={`project ${project.id} ${project.name}`}
              keywords={project.description ? [project.description] : undefined}
              icon={FolderIcon}
              onSelect={() => go(studioProjectPath(project.id))}
            >
              {project.name}
            </PaletteItem>
          ))}
        </Command.Group>

        <Command.Group heading={t("studio.palette.groups.interface")} className={GROUP}>
          <PaletteItem
            value="interface classic"
            keywords={["classic", "version", t("shell.version.classic")]}
            icon={LayoutTemplateIcon}
            onSelect={() => go(toClassicPath(pathname))}
          >
            {t("studio.palette.openClassic")}
          </PaletteItem>
        </Command.Group>

        <Command.Group heading={t("studio.palette.groups.language")} className={GROUP}>
          {locales.map((value) => (
            <PaletteItem
              key={value}
              value={`language ${value} ${t(`nav.languages.${value}`)}`}
              keywords={["language", t("nav.language")]}
              icon={LanguagesIcon}
              onSelect={() => {
                onDone();
                chooseLocale(value);
              }}
              hint={value === locale ? current : undefined}
            >
              <span lang={value}>{t(`nav.languages.${value}`)}</span>
            </PaletteItem>
          ))}
        </Command.Group>

        <Command.Group heading={t("studio.palette.groups.theme")} className={GROUP}>
          {THEMES.map(({ value, icon }) => (
            <PaletteItem
              key={value}
              value={`theme ${value} ${t(`nav.themes.${value}`)}`}
              keywords={["theme", t("nav.theme")]}
              icon={icon}
              onSelect={() => {
                onDone();
                setTheme(value);
              }}
              hint={(theme ?? "system") === value ? current : undefined}
            >
              {t(`nav.themes.${value}`)}
            </PaletteItem>
          ))}
        </Command.Group>
      </Command.List>
      <div
        aria-hidden
        className="hidden items-center gap-4 border-t border-(--studio-glass-border) px-4 py-2.5 text-xs text-muted-foreground sm:flex"
      >
        <span className="inline-flex items-center gap-1.5">
          <ArrowUpIcon className="size-3.5" />
          <ArrowDownIcon className="size-3.5" />
          {t("studio.palette.hints.navigate")}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <CornerDownLeftIcon className="size-3.5" />
          {t("studio.palette.hints.select")}
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5">
          <kbd className="font-sans">Esc</kbd>
          {t("studio.palette.hints.close")}
        </span>
      </div>
    </Command>
  );
}

/**
 * Whether a key press is the palette shortcut: ⌘K on Apple devices, Ctrl+K elsewhere. Keyboard
 * layouts that do not type a Latin letter on that key (Korean, Cyrillic, Greek...) report their
 * own character in `key`, or "Process" while an IME composes; the physical K key (`code`) counts
 * then. A Latin layout that puts another letter there (Dvorak's T) keeps its own shortcuts.
 */
export function isPaletteShortcut(event: KeyboardEvent): boolean {
  if (!(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey) {
    return false;
  }
  const key = typeof event.key === "string" ? event.key.toLowerCase() : "";
  if (key === "k") {
    return true;
  }
  return event.code === "KeyK" && !/^[a-z]$/.test(key);
}

/**
 * The ⌘K / Ctrl+K command palette (a glass dialog). The shortcut toggles it from anywhere in
 * the Studio app; focus starts in the search field and returns to where it was on close.
 */
export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("studio.palette");
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isPaletteShortcut(event)) {
        event.preventDefault();
        onOpenChange(!open);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-[oklch(0.1_0.02_265/0.45)] transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none" />
        <Dialog.Popup
          initialFocus={input}
          className={cn(
            "studio-glass studio-blur fixed top-[max(1rem,10vh)] left-1/2 z-50 w-[min(40rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-2xl bg-(--studio-glass-strong) text-foreground outline-none",
            "transition-[scale,opacity] duration-200 ease-out data-ending-style:scale-[0.98] data-ending-style:opacity-0 data-starting-style:scale-[0.98] data-starting-style:opacity-0 motion-reduce:transition-none",
          )}
        >
          <Dialog.Title className="sr-only">{t("title")}</Dialog.Title>
          <Dialog.Description className="sr-only">{t("description")}</Dialog.Description>
          <CommandPaletteContent onDone={() => onOpenChange(false)} inputRef={input} />
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
