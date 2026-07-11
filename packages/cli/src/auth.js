// Interactive sign-in via @clack/prompts. Single source for both the `login`
// command and the auto-gate that fires when a session-required call hits 401.
import { confirm, text, password, isCancel, log } from "@clack/prompts";

const isTTY = () => !!(process.stdin.isTTY && process.stdout.isTTY);

async function signIn(baseUrl, email, pwd) {
  const r = await fetch(`${baseUrl()}/api/auth/sign-in/email`, {
    method: "POST",
    headers: { "content-type": "application/json", origin: baseUrl() },
    body: JSON.stringify({ email, password: pwd }),
  });
  if (!r.ok) return { ok: false, error: `${r.status} ${await r.text()}` };
  const set = r.headers.getSetCookie?.() ?? [];
  return { ok: true, cookie: set.map((c) => c.split(";")[0]).join("; ") };
}

// Sign in and persist the session cookie.
//  - flags (email + password) present → non-interactive, no prompts
//  - otherwise prompt (TTY only); confirmFirst adds a "Do you want to log in?" gate
// Returns true on success; false if declined, cancelled, non-TTY, or sign-in failed.
export async function promptLogin({ cfg, saveCfg, baseUrl, email, password: pwd, confirmFirst = false }) {
  if (!(email && pwd)) {
    if (!isTTY()) return false;
    if (confirmFirst) {
      const go = await confirm({ message: "You're not signed in. Do you want to log in?" });
      if (isCancel(go) || !go) return false;
    }
    if (!email) {
      const v = await text({ message: "Email", validate: (s) => (s ? undefined : "Required") });
      if (isCancel(v)) return false;
      email = v;
    }
    if (!pwd) {
      const v = await password({ message: "Password", validate: (s) => (s ? undefined : "Required") });
      if (isCancel(v)) return false;
      pwd = v;
    }
  }
  const res = await signIn(baseUrl, email, pwd);
  if (!res.ok) {
    log.error(`sign-in failed: ${res.error}`);
    return false;
  }
  cfg.cookie = res.cookie;
  saveCfg(cfg);
  return true;
}
