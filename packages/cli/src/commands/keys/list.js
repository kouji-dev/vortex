// keys list — list API keys (session).
export default ({ api }) => ({
  command: "list",
  describe: "List API keys",
  handler: () => api.show("/api/keys"),
});
