/**
 * Thin fetch wrapper shared by every service module.
 *
 * It centralises the base URL, JSON handling and error shape so that feature
 * code never touches `fetch` directly.
 */

import { apiBaseUrl } from "@/lib/env";
import { getStoredToken } from "@/lib/auth-storage";

let tokenOverride: string | null | undefined;

export function setAuthTokenOverride(token: string | null | undefined): void {
  tokenOverride = token;
}

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Milliseconds before the request is aborted. Defaults to 10s. */
  timeoutMs?: number;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, timeoutMs = 10_000, headers, ...init } = options;
  const url = path.startsWith("http") ? path : `${apiBaseUrl()}${path}`;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const token = tokenOverride !== undefined ? tokenOverride : getStoredToken();
    const response = await fetch(url, {
      ...init,
      signal: options.signal ?? controller.signal,
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    const text = await response.text();
    const payload: unknown = text ? JSON.parse(text) : null;

    if (!response.ok) {
      throw new ApiError(`Request failed: ${response.status} ${url}`, response.status, payload);
    }
    return payload as T;
  } finally {
    clearTimeout(timeout);
  }
}
