#!/usr/bin/env node
// Vortex CLI — yargs + picocolors. Client over the gateway (/v1, vtx_ key) + dashboard API (/api, session).
// One file per command in ../src/commands; each exports a factory (ctx) => yargs command module.
import { readFileSync } from "node:fs";
import yargs from "yargs";
import { hideBin } from "yargs/helpers";

import { loadCfg, saveCfg } from "../src/config-store.js";
import { makeApi } from "../src/http.js";
import { die, pretty, pc } from "../src/ui.js";
import { bannerText } from "../src/banner.js";

import config from "../src/commands/config.js";
import login from "../src/commands/login.js";
import logout from "../src/commands/logout.js";
import me from "../src/commands/me.js";
import teams from "../src/commands/teams.js";
import budgets from "../src/commands/budgets.js";
import providers from "../src/commands/providers.js";
import models from "../src/commands/models.js";
import chat from "../src/commands/chat.js";
import ping from "../src/commands/ping.js";
import keys from "../src/commands/keys/index.js";
import apps from "../src/commands/apps/index.js";

const version = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
).version;

const cfg = loadCfg();
const api = makeApi(cfg, saveCfg);
const ctx = { cfg, saveCfg, api, die, pretty, pc };

const banner = process.stdout.isTTY ? bannerText(version) + "\n" : "";

let cli = yargs(hideBin(process.argv))
  .scriptName("vortex")
  .usage(`${banner}Usage: $0 <command> [options]`)
  .version(version);

for (const make of [
  config, login, logout, me,
  teams, budgets, providers,
  models, chat, ping,
  keys, apps,
])
  cli = cli.command(make(ctx));

cli
  .demandCommand(1, "run a command — see --help")
  .strict()
  .fail((msg, err) => die(msg || err?.message))
  .help()
  .wrap(null);

// Bare `vortex` → banner + help.
if (hideBin(process.argv).length === 0) {
  cli.showHelp((s) => console.log(s));
  process.exit(0);
}

try {
  await cli.parseAsync();
} catch (e) {
  die(e?.message ?? String(e));
}
