"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import type { GetPaperError, GetPaperFileData, PaperDetail } from "@/client";
import { getPaperOptions } from "@/client/@tanstack/react-query.gen";
import { client } from "@/client/client.gen";

/**
 * One paper of the library (GET /api/v1/papers/{paper_id}): its record, every analysis of it
 * (with evidence quotes and their pages) and the runs that found it. 404 `paper.not_found` when
 * the caller can open none of those runs. Pass null to wait (nothing is fetched).
 */
export function usePaper(
  paperId: string | null | undefined,
): UseQueryResult<PaperDetail, GetPaperError> {
  return useQuery({
    ...getPaperOptions({ path: { paper_id: paperId ?? "" } }),
    enabled: Boolean(paperId),
    staleTime: 60_000,
  });
}

/**
 * The URL of the paper's PDF (same origin, so the session cookie goes along), for a PDF viewer
 * or a download link. Paper ids contain slashes (`doi:10.5555/...`); they are encoded here.
 */
export function paperFileUrl(paperId: string): string {
  return client.buildUrl<GetPaperFileData>({
    url: "/api/v1/papers/{paper_id}/file",
    path: { paper_id: paperId },
  });
}
