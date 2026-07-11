export { env, ROOT } from "./config/env.js";
export type { Env } from "./config/env.js";

export {
  encryptForOrg,
  decryptForOrg,
  PLATFORM_SCOPE,
} from "./crypto/secretbox.js";

export { redis, budgetKey } from "./redis.js";

export { gcra, rlKey } from "./ratelimit/gcra.js";
export type { GcraResult, GcraOpts } from "./ratelimit/gcra.js";

export { ttlMemo } from "./cache/ttl-memo.js";
export type { TtlMemo } from "./cache/ttl-memo.js";

// Provider (host) transport adapters.
export {
  getProviderAdapter,
  getProvider,
  inferProviderId,
  resolveEndpoint,
  listEnabledProviders,
  BEDROCK_ANTHROPIC_VERSION,
  VERTEX_ANTHROPIC_VERSION,
} from "./providers/hosts/index.js";
export type {
  ProviderAdapter,
  ProviderDef,
  Capability,
  AuthStyle,
  ProviderOptions,
  EndpointCtx,
} from "./providers/hosts/index.js";

// Family (wire-envelope) adapters + SSE helpers.
export { getAdapter } from "./providers/families/index.js";
export type { FamilyAdapter } from "./providers/families/index.js";
export type { OpenAIChatCompletion } from "./providers/families/types.js";
export { iterSSELines, sseData } from "./providers/sse.js";

export {
  HOSTS,
  CATALOG,
  hostMeta,
  catalogSeedRows,
} from "./providers/catalog.js";
export type {
  ModelFamily,
  SupportedFeatures,
  Modalities,
  HostModel,
  CatalogModel,
  HostMeta,
  CatalogSeedRow,
} from "./providers/catalog.js";
