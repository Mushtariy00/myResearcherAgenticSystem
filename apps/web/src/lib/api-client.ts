import { client } from "@/client/client.gen";
import { toApiError } from "./api-error";

let configured = false;

/**
 * Wires the generated client once: same-origin relative URLs (`/api/v1/...`, routed by Caddy)
 * and every failure surfaced as an ApiError carrying the API's message code and HTTP status.
 */
export function configureApiClient(): void {
  if (configured) {
    return;
  }
  configured = true;
  client.setConfig({ credentials: "same-origin" });
  client.interceptors.error.use((error, response) => toApiError(error, response?.status));
}
