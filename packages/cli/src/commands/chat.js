// chat — one-shot chat completion via the gateway (vtx_ key).
export default ({ api, pretty }) => ({
  command: "chat <prompt>",
  describe: "One-shot chat completion",
  builder: (y) =>
    y
      .positional("prompt", { type: "string", describe: "Prompt text" })
      .option("model", { type: "string", default: "openai/gpt-4o-mini", describe: "Model id" }),
  handler: async (argv) => {
    const b = await api.withAuth("/v1/chat/completions", {
      method: "POST",
      body: JSON.stringify({ model: argv.model, messages: [{ role: "user", content: argv.prompt }] }),
    });
    pretty(b.choices?.[0]?.message?.content ?? b);
  },
});
