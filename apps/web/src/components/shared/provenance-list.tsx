"use client";

import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import type { Provenance } from "@/client";
import { cn } from "@/lib/utils";
import { CopyButton } from "./copy-button";
import { formatDuration, shortHash } from "./format";

function Hash({ value, name }: { value: string; name: string }) {
  const t = useTranslations("shared.provenance");
  return (
    <span className="flex min-w-0 items-center gap-1">
      <code className="truncate font-mono text-xs" title={value}>
        {shortHash(value)}
      </code>
      <CopyButton value={value} label={t("copyHash", { name })} size="icon-xs" />
    </span>
  );
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-0.5 @sm:grid-cols-[minmax(8rem,auto)_1fr] @sm:gap-3">
      <dt className="text-muted-foreground">{term}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export type ProvenanceListProps = {
  provenance: Provenance;
  className?: string;
};

/**
 * Where an experiment's numbers come from: the container image, code and config hashes,
 * dataset version, seed, GPU and timing. Hashes are shortened on screen and copied in full.
 */
export function ProvenanceList({ provenance, className }: ProvenanceListProps) {
  const t = useTranslations("shared.provenance");
  const format = useFormatter();
  const dateTime = (value: string) =>
    format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" });
  return (
    <dl data-slot="provenance-list" className={cn("@container grid gap-2 text-sm", className)}>
      <Row term={t("image")}>
        <Hash value={provenance.image_digest} name={t("image")} />
      </Row>
      <Row term={t("code")}>
        <Hash value={provenance.code_sha256} name={t("code")} />
      </Row>
      <Row term={t("config")}>
        <Hash value={provenance.config_sha256} name={t("config")} />
      </Row>
      <Row term={t("dataset")}>
        {t("datasetVersion", {
          dataset: provenance.dataset,
          version: provenance.dataset_version,
        })}
      </Row>
      <Row term={t("seed")}>
        <span className="font-mono tabular-nums">{provenance.seed}</span>
      </Row>
      <Row term={t("gpu")}>{provenance.gpu_name ?? t("gpuUnknown")}</Row>
      <Row term={t("gpuTime")}>
        <span className="tabular-nums">{formatDuration(provenance.gpu_seconds, format)}</span>
      </Row>
      <Row term={t("started")}>
        <time dateTime={provenance.started_at}>{dateTime(provenance.started_at)}</time>
      </Row>
      <Row term={t("finished")}>
        {provenance.finished_at ? (
          <time dateTime={provenance.finished_at}>{dateTime(provenance.finished_at)}</time>
        ) : (
          t("notFinished")
        )}
      </Row>
    </dl>
  );
}
