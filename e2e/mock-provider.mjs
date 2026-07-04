// Fake OpenAI-compatible provider for E2E. The gateway is pointed here via
// OPENAI_BASE_URL. Returns a deterministic completion + usage.
import { createServer } from "node:http";

createServer((req, res) => {
  const url = req.url ?? "";
  if (req.method === "POST" && url.includes("/chat/completions")) {
    let b = "";
    req.on("data", (d) => (b += d));
    req.on("end", () => {
      const body = JSON.parse(b || "{}");
      res.writeHead(200, { "content-type": "application/json" });
      res.end(
        JSON.stringify({
          id: "chatcmpl-mock",
          object: "chat.completion",
          created: 1,
          model: body.model || "mock",
          choices: [
            {
              index: 0,
              message: { role: "assistant", content: "Hello from the mock provider." },
              finish_reason: "stop",
            },
          ],
          usage: { prompt_tokens: 12, completion_tokens: 7, total_tokens: 19 },
        }),
      );
    });
  } else if (url.includes("/models")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ object: "list", data: [{ id: "gpt-4o-mini" }] }));
  } else {
    res.writeHead(404);
    res.end("{}");
  }
}).listen(9099, () => console.log("mock provider on :9099"));
