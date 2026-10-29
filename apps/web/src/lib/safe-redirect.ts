const BASE = "http://app.invalid";

/**
 * Where to go after signing in. Only same-site paths are allowed, so a crafted
 * `/login?next=https://evil.example` cannot bounce the user to another site.
 */
export function safeNextPath(value: string | null | undefined, fallback = "/"): string {
  if (!value?.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return fallback;
  }
  // Control characters and whitespace have no place in our paths.
  for (const char of value) {
    const code = char.charCodeAt(0);
    if (code <= 0x20 || code === 0x7f) {
      return fallback;
    }
  }
  let url: URL;
  try {
    url = new URL(value, BASE);
  } catch {
    return fallback;
  }
  // Dot segments are resolved first: "/.//evil.example" normalises to "//evil.example", which a
  // browser reads as another host, so the check runs on the normalised path.
  const path = url.pathname;
  if (
    url.origin !== BASE ||
    path.startsWith("//") ||
    path.startsWith("/\\") ||
    path.startsWith("/api/") ||
    path === "/login" ||
    path === "/studio/login"
  ) {
    return fallback;
  }
  return `${path}${url.search}${url.hash}`;
}
