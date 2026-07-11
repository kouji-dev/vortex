// teams — list teams (session).
export default ({ api }) => ({
  command: "teams",
  describe: "List teams",
  handler: () => api.show("/api/teams"),
});
