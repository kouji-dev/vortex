// providers — list provider credentials (session).
export default ({ api }) => ({
  command: "providers",
  describe: "List provider credentials",
  handler: () => api.show("/api/providers"),
});
