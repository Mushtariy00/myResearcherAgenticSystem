import type admin from "../../messages/en/admin.json";
import type core from "../../messages/en/core.json";
import type dashboard from "../../messages/en/dashboard.json";
import type notifications from "../../messages/en/notifications.json";
import type papers from "../../messages/en/papers.json";
import type profile from "../../messages/en/profile.json";
import type projects from "../../messages/en/projects.json";
import type runs from "../../messages/en/runs.json";
import type shell from "../../messages/en/shell.json";
import type studio from "../../messages/en/studio.json";
import type studioRun from "../../messages/en/studioRun.json";
import type studioWork from "../../messages/en/studioWork.json";
import type wizard from "../../messages/en/wizard.json";
import type { Locale } from "./config";

// One type per area file (see messages.ts); English is the reference for key names.
type Messages = typeof core &
  typeof shell &
  typeof dashboard &
  typeof projects &
  typeof wizard &
  typeof runs &
  typeof papers &
  typeof admin &
  typeof notifications &
  typeof profile &
  typeof studio &
  typeof studioRun &
  typeof studioWork;

// Typed message keys: `t("missing.key")` fails the type check.
declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
    Messages: Messages;
  }
}
