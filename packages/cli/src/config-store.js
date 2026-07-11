// Persisted CLI config: ~/.vortex/config.json (baseUrl + gateway key + session cookie).
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const CFG_DIR = join(homedir(), ".vortex");
const CFG = join(CFG_DIR, "config.json");

const DEFAULTS = { baseUrl: "http://localhost:8080", apiKey: "", cookie: "" };

export function loadCfg() {
  if (!existsSync(CFG)) return { ...DEFAULTS };
  return { ...DEFAULTS, ...JSON.parse(readFileSync(CFG, "utf8")) };
}

export function saveCfg(c) {
  if (!existsSync(CFG_DIR)) mkdirSync(CFG_DIR, { recursive: true });
  writeFileSync(CFG, JSON.stringify(c, null, 2));
}
