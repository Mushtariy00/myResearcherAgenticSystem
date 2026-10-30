"use client";

import { createContext, useContext } from "react";

/**
 * The page's CSP nonce (src/lib/csp.ts), for the few inline scripts this codebase writes. Set
 * once by Providers from the root layout; undefined in tests and outside a request.
 */
export const NonceContext = createContext<string | undefined>(undefined);

export function useNonce(): string | undefined {
  return useContext(NonceContext);
}
