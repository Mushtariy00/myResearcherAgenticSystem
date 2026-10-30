/**
 * Marks <html> as a Studio page before the first paint of a full page load (the body and the
 * scrollbars take the Studio tokens at once). StudioProviders keeps it in sync on client
 * navigations and removes it when the visitor leaves Studio.
 */
export const STUDIO_SCOPE_SCRIPT = `document.documentElement.setAttribute("data-ui","studio")`;
