// apps create — create an app (session). --kind is enum-validated by the parser.
export default ({ api }) => ({
  command: "create",
  describe: "Create an app",
  builder: (y) =>
    y
      .option("name", { type: "string", demandOption: true, describe: "App name" })
      .option("kind", {
        choices: ["service", "personal"],
        default: "service",
        describe: "App kind",
      }),
  handler: (argv) =>
    api.show("/api/apps", {
      method: "POST",
      body: JSON.stringify({ name: argv.name, kind: argv.kind }),
    }),
});
