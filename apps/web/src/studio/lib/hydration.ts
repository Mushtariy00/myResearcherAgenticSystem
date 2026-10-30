"use client";

import { useEffect, useState } from "react";

let appHydrated = false;

/**
 * Whether this component mounted after the page hydrated (a client-side mount, such as after a
 * navigation or once data arrived), read once at mount. It is false while server rendering and
 * hydrating, so entrance animations never hide server-rendered content or change its markup.
 */
export function useMountedAfterHydration(): boolean {
  const [afterHydration] = useState(() => appHydrated);
  useEffect(() => {
    appHydrated = true;
  }, []);
  return afterHydration;
}
