// ping — gateway health check.
export default ({ api }) => ({
  command: "ping",
  describe: "Health check",
  handler: async () => {
    const r = await fetch(`${api.baseUrl()}/health`);
    console.log(r.status, await r.text());
  },
});
