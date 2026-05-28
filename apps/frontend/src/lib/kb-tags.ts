// apps/frontend/src/lib/kb-tags.ts
//
// Pure helpers for KB tag edit + filter. Tags travel as a JSON array on the
// `tags` column of `knowledge_bases`; the editor surfaces them as a comma-
// separated input, the list page renders them as filter chips.

/** Parse a free-text editor value into a clean, deduped tag list. */
export function parseTagsInput(raw: string): string[] {
  if (!raw) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const piece of raw.split(',')) {
    const t = piece.trim().toLowerCase()
    if (!t) continue
    if (seen.has(t)) continue
    seen.add(t)
    out.push(t)
  }
  return out
}

/** Inverse — render an array back as the editor string. */
export function formatTags(tags: readonly string[] | null | undefined): string {
  if (!tags || tags.length === 0) return ''
  return tags.join(', ')
}

/** Collect every distinct tag across a list of KBs (sorted). */
export function collectAllTags(
  items: readonly { tags?: readonly string[] | null }[],
): string[] {
  const set = new Set<string>()
  for (const it of items) {
    for (const t of it.tags ?? []) {
      const v = t.trim().toLowerCase()
      if (v) set.add(v)
    }
  }
  return [...set].sort()
}

/** Toggle one tag in/out of an active-filter list (pure). */
export function toggleTag(active: readonly string[], tag: string): string[] {
  const t = tag.trim().toLowerCase()
  if (!t) return [...active]
  return active.includes(t) ? active.filter((x) => x !== t) : [...active, t]
}

/** AND-match: item must carry every active tag. Empty filter → keep all. */
export function filterByTags<T extends { tags?: readonly string[] | null }>(
  items: readonly T[],
  active: readonly string[],
): T[] {
  if (active.length === 0) return [...items]
  const norm = active.map((t) => t.toLowerCase())
  return items.filter((it) => {
    const tags = (it.tags ?? []).map((t) => t.toLowerCase())
    return norm.every((t) => tags.includes(t))
  })
}
