// Single request transport bound to the active config.
//  api(path, init)          → /api/* call: session cookie if logged in, else the
//                             vtx_ key (headless). Returns parsed body.
//  api.show(path, init)      → fetch + pretty-print the body (the common "get & display" path)
//  api.withAuth(path, init)  → force gateway bearer key (/v1/*, key-only)
//  api.baseUrl() / api.apiKey() → effective values: env (VORTEX_BASE_URL /
//                              VORTEX_API_KEY) wins over the config file, never persisted.
import { die, pretty } from "./ui.js";
import { promptLogin } from "./auth.js";

export function makeApi(cfg, saveCfg) {
  const baseUrl = () => process.env.VORTEX_BASE_URL || cfg.baseUrl;
  const apiKey = () => process.env.VORTEX_API_KEY || cfg.apiKey;

  function authHeaders() {
    const key = apiKey();
    if (!key) die("no api key — set VORTEX_API_KEY or run: vortex config --key vtx_…");
    return { authorization: `Bearer ${key}` };
  }

  async function api(path, init = {}, retried = false) {
    const headers = {
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...(init.headers || {}),
    };
    // Prefer an active login session; fall back to the API key for headless use.
    if (cfg.cookie) headers.cookie = cfg.cookie;
    else if (!headers.authorization && apiKey()) headers.authorization = `Bearer ${apiKey()}`;

    const r = await fetch(`${baseUrl()}${path}`, { ...init, headers });
    if (r.status === 401 || r.status === 409) {
      // A key-authed call that fails is a bad/insufficient key, not a missing
      // session — surface it, don't prompt for an interactive login.
      if (headers.authorization) die(`${r.status} ${await r.text()}`);
      // No session and no key → offer to log in, then retry once.
      if (r.status === 401 && !retried) {
        const ok = await promptLogin({ cfg, saveCfg, baseUrl, confirmFirst: true });
        if (ok) return api(path, init, true);
      }
      die("not signed in — run: vortex login (or set VORTEX_API_KEY)");
    }
    if (!r.ok) die(`${r.status} ${await r.text()}`);
    return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
  }

  api.withAuth = (path, init = {}) =>
    api(path, { ...init, headers: { ...authHeaders(), ...(init.headers || {}) } });
  api.show = async (path, init) => pretty(await api(path, init));
  api.baseUrl = baseUrl;
  api.apiKey = apiKey;

  return api;
}
