import { AsyncLocalStorage } from "node:async_hooks";

/**
 * Per-request memoization store. Unlike `ttlMemo` (cross-request, time-bounded),
 * this caches only for the duration of ONE request — so values that must always
 * reflect the latest state (e.g. a budget pool that an admin just changed) are
 * re-resolved on every request, while repeated lookups *within* a request (a
 * pre-check + its post-commit) share a single result. No arg-threading needed.
 */
const als = new AsyncLocalStorage<Map<string, Promise<unknown>>>();

/** Run `fn` with a fresh per-request cache in scope (gateway middleware). */
export function runWithRequestCache<T>(fn: () => T): T {
  return als.run(new Map(), fn);
}

/**
 * Return the cached value for `key` within the current request, else load +
 * cache it. Outside a request scope (no store) it just calls `load` (no cache).
 * Caches the promise → concurrent lookups in a request share one load.
 */
export function requestMemo<T>(key: string, load: () => Promise<T>): Promise<T> {
  const store = als.getStore();
  if (!store) return load();
  const hit = store.get(key);
  if (hit) return hit as Promise<T>;
  const p = load();
  store.set(key, p);
  return p;
}
