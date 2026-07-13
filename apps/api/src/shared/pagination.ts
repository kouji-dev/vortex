import type { Context } from "hono";
import { z } from "zod";
import type { AppEnv } from "./ctx.js";

/** Standard list-endpoint page params: `?limit=` (1–100, default 50) and `?offset=` (≥0, default 0). */
export const pageSchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(50),
  offset: z.coerce.number().int().min(0).default(0),
});

export type Page = z.infer<typeof pageSchema>;

/**
 * Parse `limit`/`offset` from the request query string. Invalid values fall
 * back to the defaults rather than erroring — pagination is never fatal.
 *
 *   const page = parsePage(c);
 *   …query.limit(page.limit).offset(page.offset)
 */
export function parsePage(c: Context<AppEnv>): Page {
  const parsed = pageSchema.safeParse({
    limit: c.req.query("limit"),
    offset: c.req.query("offset"),
  });
  return parsed.success ? parsed.data : { limit: 50, offset: 0 };
}

/** Standard list-endpoint response envelope. */
export type PageEnvelope<T> = { items: T[]; limit: number; offset: number };

/** Wrap a page of rows in the standard envelope. */
export function pageEnvelope<T>(items: T[], page: Page): PageEnvelope<T> {
  return { items, limit: page.limit, offset: page.offset };
}
