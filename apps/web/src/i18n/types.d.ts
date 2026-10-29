import type messages from "../../messages/en.json";
import type { Locale } from "./config";

// Typed message keys: `t("missing.key")` fails the type check.
declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
    Messages: typeof messages;
  }
}
