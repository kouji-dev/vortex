/**
 * Reusable in-process TTL memoizer. Caches the in-flight **promise** (not just
 * the resolved value) so concurrent misses for the same key share one load —
 * no cache stampede. A rejected load is evicted so transient errors aren't
 * cached for the whole TTL.
 *
 * Per-process only (each replica has its own map). Use `.invalidate(key)` after
 * a mutation that changes the cached value; `.clear()` drops everything.
 *
 * @example
 *   const getUser = ttlMemo(30_000, (id: string) => db.loadUser(id));
 *   await getUser("u1");        // loads
 *   await getUser("u1");        // cached
 *   getUser.invalidate("u1");   // next call reloads
 */
export interface TtlMemo<K, V> {
  (key: K): Promise<V>;
  /** Drop a single key from the cache. */
  invalidate(key: K): void;
  /** Drop every cached entry. */
  clear(): void;
}

export function ttlMemo<K, V>(
  ttlMs: number,
  load: (key: K) => Promise<V>,
): TtlMemo<K, V> {
  const store = new Map<K, { v: Promise<V>; exp: number }>();

  const memo = ((key: K): Promise<V> => {
    const now = Date.now();
    const hit = store.get(key);
    if (hit && hit.exp > now) return hit.v;

    const v = load(key);
    store.set(key, { v, exp: now + ttlMs });
    // Don't cache a rejected load — evict if this exact entry failed.
    v.catch(() => {
      const cur = store.get(key);
      if (cur && cur.v === v) store.delete(key);
    });
    return v;
  }) as TtlMemo<K, V>;

  memo.invalidate = (key: K) => {
    store.delete(key);
  };
  memo.clear = () => {
    store.clear();
  };
  return memo;
}
