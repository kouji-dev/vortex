// logout — clear the stored session.
export default ({ cfg, saveCfg, api, pretty }) => ({
  command: "logout",
  describe: "Clear session",
  handler: async () => {
    if (cfg.cookie)
      await fetch(`${api.baseUrl()}/api/auth/sign-out`, {
        method: "POST",
        headers: { cookie: cfg.cookie },
      }).catch(() => {});
    cfg.cookie = "";
    saveCfg(cfg);
    pretty({ signedIn: false });
  },
});
