/**
 * Container liveness probe.
 *
 * Deliberately free of any backend call: the frontend must be reported healthy
 * whenever its own Node process can serve a request, otherwise a backend outage
 * would make Docker restart a perfectly working frontend.
 */
export const dynamic = "force-static";

export function GET(): Response {
  return new Response("ok\n", {
    status: 200,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
