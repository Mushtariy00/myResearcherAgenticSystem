/** A UUID as FastAPI reads one from a path: 32 hex digits, with or without the hyphens. */
const UUID = /^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$/i;

/**
 * Project and run ids are UUIDs. A route param that is not one (a truncated or mistyped link)
 * names nothing, so its page is "not found" rather than the API's 422 about invalid fields.
 */
export function isUuid(value: string): boolean {
  return UUID.test(value);
}
