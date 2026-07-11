// me — current user + org membership.
export default ({ api }) => ({
  command: "me",
  describe: "Current user + org membership",
  handler: () => api.show("/api/me"),
});
