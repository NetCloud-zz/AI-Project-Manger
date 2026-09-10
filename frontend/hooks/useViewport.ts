"use client";

import { useSyncExternalStore } from "react";

export const BREAKPOINTS = {
  tablet: 768,
  laptop: 1024,
  desktop: 1440,
} as const;

export type Viewport = "mobile" | "tablet" | "laptop" | "desktop";

const QUERIES: Array<{ query: string; viewport: Viewport }> = [
  { query: `(min-width: ${BREAKPOINTS.desktop}px)`, viewport: "desktop" },
  { query: `(min-width: ${BREAKPOINTS.laptop}px)`, viewport: "laptop" },
  { query: `(min-width: ${BREAKPOINTS.tablet}px)`, viewport: "tablet" },
];

function subscribe(onStoreChange: () => void): () => void {
  const lists = QUERIES.map(({ query }) => window.matchMedia(query));
  lists.forEach((list) => list.addEventListener("change", onStoreChange));
  return () => lists.forEach((list) => list.removeEventListener("change", onStoreChange));
}

function getSnapshot(): Viewport {
  for (const { query, viewport } of QUERIES) {
    if (window.matchMedia(query).matches) return viewport;
  }
  return "mobile";
}

/** Server render assumes mobile so the markup matches the mobile-first stylesheet. */
function getServerSnapshot(): Viewport {
  return "mobile";
}

/**
 * Current viewport bucket, matching the breakpoints in globals.css.
 *
 * Needed because Ant Design's theme is a plain JS object that CSS media queries
 * cannot reach — control heights have to be switched in the provider.
 */
export function useViewport(): Viewport {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function useIsDesktop(): boolean {
  const viewport = useViewport();
  return viewport === "laptop" || viewport === "desktop";
}
