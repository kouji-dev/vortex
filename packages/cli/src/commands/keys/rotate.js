// keys rotate <id> — rotate an API key (session).
export default ({ api }) => ({
  command: "rotate <id>",
  describe: "Rotate an API key",
  builder: (y) => y.positional("id", { type: "string", describe: "Key id" }),
  handler: (argv) => api.show(`/api/keys/${argv.id}/rotate`, { method: "POST" }),
});
