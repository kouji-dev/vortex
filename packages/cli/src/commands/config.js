// config — show or set gateway base URL + API key.
export default ({ cfg, saveCfg, api, pretty }) => ({
  command: "config",
  describe: "Show or set base URL + gateway key",
  builder: (y) =>
    y
      .option("url", { type: "string", describe: "Gateway base URL" })
      .option("key", { type: "string", describe: "Gateway API key (vtx_…)" }),
  handler: (argv) => {
    if (argv.url) cfg.baseUrl = argv.url;
    if (argv.key) cfg.apiKey = argv.key;
    if (argv.url || argv.key) saveCfg(cfg);
    // Report effective (env-overridden) values + where the key resolves from.
    const key = api.apiKey();
    pretty({
      baseUrl: api.baseUrl(),
      apiKey: key ? key.slice(0, 12) + "…" : "",
      apiKeySource: process.env.VORTEX_API_KEY
        ? "env (VORTEX_API_KEY)"
        : cfg.apiKey
          ? "config (~/.vortex/config.json)"
          : "none",
      signedIn: !!cfg.cookie,
    });
  },
});
