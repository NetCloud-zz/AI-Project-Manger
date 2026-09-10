/**
 * Runtime configuration for the frontend.
 *
 * `NEXT_PUBLIC_API_BASE_URL` is what the browser calls (routed through Nginx in
 * Docker). `INTERNAL_API_BASE_URL` is what server components use to reach the
 * backend directly over the compose network, skipping the proxy hop.
 */

const trimTrailingSlash = (value: string): string => value.replace(/\/+$/, "");

/** Treat unset and empty string differently: empty means same-origin (Docker/Nginx). */
function resolvePublicApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (raw === undefined) {
    return "http://localhost:8000";
  }
  return trimTrailingSlash(raw);
}

export const PUBLIC_API_BASE_URL = resolvePublicApiBase();

export const INTERNAL_API_BASE_URL = trimTrailingSlash(
  process.env.INTERNAL_API_BASE_URL ??
    (PUBLIC_API_BASE_URL !== "" ? PUBLIC_API_BASE_URL : "http://backend:8000"),
);

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "研发项目管理 Agent";

/**
 * Browser: same-origin when NEXT_PUBLIC is empty (Nginx entry).
 * Direct :3000 dev without Nginx falls back to :8000 on the same host.
 */
export const apiBaseUrl = (): string => {
  if (typeof window === "undefined") {
    return INTERNAL_API_BASE_URL;
  }
  if (PUBLIC_API_BASE_URL !== "") {
    return PUBLIC_API_BASE_URL;
  }
  if (window.location.port === "3000") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "";
};
