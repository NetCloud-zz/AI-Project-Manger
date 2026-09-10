"use client";

import { useRouter } from "next/navigation";
import { useCallback, useTransition } from "react";

interface UseRefreshResult {
  refresh: () => void;
  pending: boolean;
}

/**
 * Re-run the current route's server components.
 *
 * Data lives in server components, so refreshing the route is how a client
 * component asks for fresh data without duplicating the fetch on the client.
 */
export function useRefresh(): UseRefreshResult {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  const refresh = useCallback(() => {
    startTransition(() => router.refresh());
  }, [router]);

  return { refresh, pending };
}
