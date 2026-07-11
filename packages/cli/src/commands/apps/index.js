// apps — parent command; verbs are real subcommands (one file each).
import list from "./list.js";
import create from "./create.js";

export default (ctx) => ({
  command: "apps",
  describe: "Manage apps",
  builder: (y) =>
    y
      .command(list(ctx))
      .command(create(ctx))
      .demandCommand(1, "apps subcommand required: list | create")
      .strict(),
  handler: () => {},
});
