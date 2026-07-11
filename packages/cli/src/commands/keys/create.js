// keys create — mint an API key (session).
export default ({ api }) => ({
  command: "create",
  describe: "Create an API key",
  builder: (y) =>
    y.option("name", { type: "string", demandOption: true, describe: "Key name" }),
  handler: (argv) =>
    api.show("/api/keys", { method: "POST", body: JSON.stringify({ name: argv.name }) }),
});
