"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { type ReactNode, useState } from "react";
import { NonceContext } from "@/components/nonce";
import { Toaster } from "@/components/ui/sonner";
import { configureApiClient } from "@/lib/api-client";
import { toApiError } from "@/lib/api-error";
import { signInRedirectFor } from "@/lib/auth-redirect";

configureApiClient();

/**
 * An expired or revoked session makes the API answer 401: go back to the sign-in page of the
 * interface (Classic or Studio) the user is in, and from there to this page. Not again right
 * after coming back from it (see auth-redirect.ts): then the page shows the errors instead.
 */
function redirectOnUnauthorized(error: unknown): void {
  if (typeof window === "undefined") {
    return;
  }
  const target = signInRedirectFor(error, window.location);
  if (target) {
    window.location.assign(target);
  }
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

/** `nonce`: the page's CSP nonce, for next-themes' script and our own inline scripts. */
export function Providers({ children, nonce }: { children: ReactNode; nonce?: string }) {
  const [queryClient] = useState(makeQueryClient);
  return (
    <NonceContext value={nonce}>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
        nonce={nonce}
      >
        <QueryClientProvider client={queryClient}>
          {children}
          <Toaster closeButton richColors position="top-right" />
        </QueryClientProvider>
      </ThemeProvider>
    </NonceContext>
  );
}
