// keys revoke <id> — revoke an API key (session).
export default ({ api }) => ({
  command: "revoke <id>",
  describe: "Revoke an API key",
  builder: (y) => y.positional("id", { type: "string", describe: "Key id" }),
  handler: (argv) => api.show(`/api/keys/${argv.id}/revoke`, { method: "POST" }),
});
