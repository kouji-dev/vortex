// login — sign in (prompts for email/password if flags omitted) and store the session.
import { promptLogin } from "../auth.js";

export default ({ cfg, saveCfg, api, die }) => ({
  command: "login",
  describe: "Sign in (prompts if --email/--password omitted)",
  builder: (y) =>
    y
      .option("email", { type: "string", describe: "Account email" })
      .option("password", { type: "string", describe: "Account password (omit to be prompted)" }),
  handler: async (argv) => {
    const ok = await promptLogin({
      cfg,
      saveCfg,
      baseUrl: api.baseUrl,
      email: argv.email,
      password: argv.password,
    });
    if (!ok) die("login cancelled or failed");
    await api.show("/api/me");
  },
});
