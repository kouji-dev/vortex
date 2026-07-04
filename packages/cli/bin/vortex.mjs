#!/usr/bin/env node
// Vortex CLI — client over the gateway (/v1, vtx_ key) + dashboard API (/api, session).
// No deps: Node 22 global fetch. Config in ~/.vortex/config.json.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const CFG_DIR = join(homedir(), ".vortex");
const CFG = join(CFG_DIR, "config.json");

function loadCfg() {
  if (!existsSync(CFG))
    return { baseUrl: "http://localhost:8080", apiKey: "", cookie: "" };
  return { baseUrl: "http://localhost:8080", apiKey: "", cookie: "", ...JSON.parse(readFileSync(CFG, "utf8")) };
}
function saveCfg(c) {
  if (!existsSync(CFG_DIR)) mkdirSync(CFG_DIR, { recursive: true });
  writeFileSync(CFG, JSON.stringify(c, null, 2));
}
function flag(a, n) {
  const i = a.indexOf(`--${n}`);
  return i >= 0 ? a[i + 1] : undefined;
}
function die(m) {
  console.error(`✗ ${m}`);
  process.exit(1);
}
function pretty(x) {
  console.log(typeof x === "string" ? x : JSON.stringify(x, null, 2));
}

const [cmd, ...args] = process.argv.slice(2);
const cfg = loadCfg();

// dashboard (session cookie) request
async function api(path, init = {}) {
  const r = await fetch(`${cfg.baseUrl}${path}`, {
    ...init,
    headers: {
      ...(cfg.cookie ? { cookie: cfg.cookie } : {}),
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...(init.headers || {}),
    },
  });
  if (r.status === 401 || r.status === 409)
    die("not signed in — run: vortex login --email … --password …");
  if (!r.ok) die(`${r.status} ${await r.text()}`);
  return r.headers.get("content-type")?.includes("json") ? r.json() : r.text();
}
// gateway (vtx_ key) request
function gwAuth() {
  if (!cfg.apiKey) die("no api key — run: vortex config --key vtx_…");
  return { authorization: `Bearer ${cfg.apiKey}`, "content-type": "application/json" };
}

const commands = {
  help() {
    console.log(`vortex <command>

  Config / auth
    config [--url URL] [--key vtx_…]     show/set base URL + gateway key
    login --email E --password P         sign in (stores session)
    logout                               clear session
    me                                   current user + org membership

  Dashboard (session)
    keys [create --name N] [rotate ID] [revoke ID]
    apps [create --name N --kind service|personal]
    teams                                list teams
    budgets                              team defaults + per-member spend
    providers                            provider credentials

  Gateway (vtx_ key)
    models                               list models
    chat "<prompt>" [--model M]          one-shot completion
    ping                                 health check
`);
  },

  config() {
    const url = flag(args, "url");
    const key = flag(args, "key");
    if (url) cfg.baseUrl = url;
    if (key) cfg.apiKey = key;
    if (url || key) saveCfg(cfg);
    pretty({
      baseUrl: cfg.baseUrl,
      apiKey: cfg.apiKey ? cfg.apiKey.slice(0, 12) + "…" : "",
      signedIn: !!cfg.cookie,
    });
  },

  async login() {
    const email = flag(args, "email");
    const password = flag(args, "password");
    if (!email || !password) die("usage: vortex login --email E --password P");
    const r = await fetch(`${cfg.baseUrl}/api/auth/sign-in/email`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: cfg.baseUrl },
      body: JSON.stringify({ email, password }),
    });
    if (!r.ok) die(`sign-in failed: ${r.status} ${await r.text()}`);
    const set = r.headers.getSetCookie?.() ?? [];
    cfg.cookie = set.map((c) => c.split(";")[0]).join("; ");
    saveCfg(cfg);
    const me = await api("/api/me");
    pretty({ signedIn: true, user: me.user, member: me.member });
  },

  async logout() {
    if (cfg.cookie)
      await fetch(`${cfg.baseUrl}/api/auth/sign-out`, {
        method: "POST",
        headers: { cookie: cfg.cookie },
      }).catch(() => {});
    cfg.cookie = "";
    saveCfg(cfg);
    pretty({ signedIn: false });
  },

  async me() {
    pretty(await api("/api/me"));
  },

  async keys() {
    const sub = args[0];
    if (sub === "create") {
      const name = flag(args, "name");
      pretty(await api("/api/keys", { method: "POST", body: JSON.stringify({ name }) }));
    } else if (sub === "rotate") {
      pretty(await api(`/api/keys/${args[1]}/rotate`, { method: "POST" }));
    } else if (sub === "revoke") {
      pretty(await api(`/api/keys/${args[1]}/revoke`, { method: "POST" }));
    } else {
      pretty(await api("/api/keys"));
    }
  },

  async apps() {
    if (args[0] === "create") {
      const name = flag(args, "name");
      const kind = flag(args, "kind") ?? "service";
      pretty(await api("/api/apps", { method: "POST", body: JSON.stringify({ name, kind }) }));
    } else {
      pretty(await api("/api/apps"));
    }
  },

  async teams() {
    pretty(await api("/api/teams"));
  },
  async budgets() {
    pretty(await api("/api/budgets"));
  },
  async providers() {
    pretty(await api("/api/providers"));
  },

  async models() {
    const r = await fetch(`${cfg.baseUrl}/v1/models`, { headers: gwAuth() });
    if (!r.ok) die(`${r.status} ${await r.text()}`);
    const b = await r.json();
    for (const m of b.data ?? b.models ?? []) console.log(m.id ?? m);
  },

  async chat() {
    const prompt = args.find((a) => !a.startsWith("--"));
    if (!prompt) die('usage: vortex chat "<prompt>" [--model M]');
    const model = flag(args, "model") ?? "openai/gpt-4o-mini";
    const r = await fetch(`${cfg.baseUrl}/v1/chat/completions`, {
      method: "POST",
      headers: gwAuth(),
      body: JSON.stringify({ model, messages: [{ role: "user", content: prompt }] }),
    });
    if (!r.ok) die(`${r.status} ${await r.text()}`);
    const b = await r.json();
    pretty(b.choices?.[0]?.message?.content ?? b);
  },

  async ping() {
    const r = await fetch(`${cfg.baseUrl}/health`);
    console.log(r.status, await r.text());
  },
};

Promise.resolve((commands[cmd] ?? commands.help)()).catch((e) => die(e.message));
