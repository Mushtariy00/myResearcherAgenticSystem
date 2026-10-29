"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { type ReactNode, useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { configureApiClient } from "@/lib/api-client";
import { toApiError } from "@/lib/api-error";
import { loginPathFor } from "@/lib/ui-version";

configureApiClient();

/**
 * An expired or revoked session makes the API answer 401: go back to the sign-in page of the
 * interface (Classic or Studio) the user is in.
 */
function redirectOnUnauthorized(error: unknown): void {
  if (typeof window === "undefined" || toApiError(error).status !== 401) {
    return;
  }
  const { pathname, search } = window.location;
  window.location.assign(
    `${loginPathFor(pathname)}?next=${encodeURIComponent(`${pathname}${search}`)}`,
  );
}

function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({ onError: redirectOnUnauthorized }),
    mutationCache: new MutationCache({ onError: redirectOnUnauthorized }),
    defaultOptions: {
      queries: {
        staleTime: 10_000,
        // Client errors (403, 404, 409...) will not change on retry; server hiccups might.
        retry: (failureCount, error) => {
          const status = toApiError(error).status;
          return (status === undefined || status >= 500) && failureCount < 2;
        },
      },
      mutations: { retry: false },
    },
  });
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        {children}
        <Toaster closeButton richColors position="top-right" />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
