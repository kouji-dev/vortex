// budgets — team defaults + per-member spend (session).
export default ({ api }) => ({
  command: "budgets",
  describe: "Team defaults + per-member spend",
  handler: () => api.show("/api/budgets"),
});
