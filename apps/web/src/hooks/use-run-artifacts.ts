"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { ArtifactList, ArtifactOut, GetArtifactData, ListRunArtifactsError } from "@/client";
import { listRunArtifactsOptions } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";

export type RunArtifacts = {
  /** The artifact list query: pending and error states, `refetch`. */
  query: UseQueryResult<ArtifactList, ListRunArtifactsError>;
  /** Every file the run's latest coding, experiment and writing outputs make, in that order. */
  artifacts: readonly ArtifactOut[];
  /** The artifacts of each stage that has some. */
  byStage: Readonly<Record<string, readonly ArtifactOut[]>>;
  /** The zip of all generated code files, if the coding stage made one. */
  codeArchive: ArtifactOut | undefined;
  /** Some artifact comes from generated demo output: show the Demo badge. */
  demo: boolean;
};

const NO_ARTIFACTS: readonly ArtifactOut[] = [];

/**
 * A run's downloadable files (`GET /runs/{id}/artifacts`). They follow the latest outputs, so
 * `useRunView` on the same page refetches them when stage events arrive. Link each one with
 * `artifactUrl(artifact.id)`.
 */
export function useRunArtifacts(runId: string, options: { enabled?: boolean } = {}): RunArtifacts {
  const query = useQuery({
    ...listRunArtifactsOptions({ path: { run_id: runId } }),
    enabled: options.enabled ?? true,
  });
  const data = query.data;
  const derived = useMemo(() => {
    const artifacts = data?.items ?? NO_ARTIFACTS;
    const byStage: Record<string, ArtifactOut[]> = {};
    for (const artifact of artifacts) {
      const list = byStage[artifact.stage] ?? [];
      list.push(artifact);
      byStage[artifact.stage] = list;
    }
    return {
      artifacts,
      byStage,
      codeArchive: artifacts.find((artifact) => artifact.kind === "code_archive"),
    };
  }, [data]);
  return { query, ...derived, demo: data?.demo ?? false };
}

/**
 * Where to download an artifact (`GET /api/v1/artifacts/{id}`, same origin, so the session cookie
 * goes along). The API streams it as an attachment with `nosniff`: use it as a link's `href`.
 */
export function artifactUrl(artifactId: string): string {
  return client.buildUrl<GetArtifactData>({
    url: "/api/v1/artifacts/{artifact_id}",
    path: { artifact_id: artifactId },
  });
}
