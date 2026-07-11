// models — list models available via the gateway (vtx_ key).
export default ({ api }) => ({
  command: "models",
  describe: "List available models",
  handler: async () => {
    const b = await api.withAuth("/v1/models");
    for (const m of b.data ?? b.models ?? []) console.log(m.id ?? m);
  },
});
