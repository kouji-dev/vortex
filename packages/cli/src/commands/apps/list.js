// apps list — list apps (session).
export default ({ api }) => ({
  command: "list",
  describe: "List apps",
  handler: () => api.show("/api/apps"),
});
