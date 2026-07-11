// keys — parent command. The concrete verbs are real subcommands (one file each),
// so `vortex keys frob` is rejected by the parser, not the handler.
import list from "./list.js";
import create from "./create.js";
import rotate from "./rotate.js";
import revoke from "./revoke.js";

export default (ctx) => ({
  command: "keys",
  describe: "Manage API keys",
  builder: (y) =>
    y
      .command(list(ctx))
      .command(create(ctx))
      .command(rotate(ctx))
      .command(revoke(ctx))
      .demandCommand(1, "keys subcommand required: list | create | rotate | revoke")
      .strict(),
  handler: () => {},
});
