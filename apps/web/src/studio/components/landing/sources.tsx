import { useTranslations } from "next-intl";
import { Marquee } from "@/studio/components/effects/marquee";
import { SectionHeading } from "./section-heading";

/** Scholarly sources the literature stage is built around (names only, no logos). */
export const DATA_SOURCES = [
  "arXiv",
  "Semantic Scholar",
  "OpenAlex",
  "Crossref",
  "CORE",
  "Unpaywall",
] as const;

export function LandingSources() {
  const t = useTranslations("studio.landing.sources");
  return (
    <section
      id="sources"
      aria-labelledby="studio-sources-title"
      className="scroll-mt-20 px-4 py-20 sm:px-6 lg:py-24"
    >
      <div className="mx-auto grid w-full max-w-6xl gap-10">
        <SectionHeading
          id="studio-sources-title"
          eyebrow={t("eyebrow")}
          title={t("title")}
          subtitle={t("subtitle")}
          tone="success"
        />
        <Marquee label={t("label")} duration={36}>
          {DATA_SOURCES.map((source) => (
            <li
              key={source}
              className="studio-glass inline-flex h-14 shrink-0 items-center gap-3 rounded-2xl px-6 text-base font-semibold tracking-tight whitespace-nowrap text-foreground"
            >
              <span
                aria-hidden
                className="size-2 rounded-full bg-linear-to-br from-(--aurora-cyan) to-(--aurora-violet)"
              />
              {source}
            </li>
          ))}
        </Marquee>
      </div>
    </section>
  );
}
