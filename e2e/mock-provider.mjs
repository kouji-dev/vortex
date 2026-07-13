// Fake OpenAI-compatible provider for E2E. The gateway is pointed here via
// OPENAI_BASE_URL. Returns a deterministic completion + usage.
//
// Test controls (POST /__control JSON):
//   { fail500Times: N }  → the next N chat requests answer 500
//   { hangMs: N }        → the next ONE chat request stalls N ms before replying
//   { streamChunks: N, streamDelayMs: M } → shape of streamed responses
//   {}                   → reset all controls to defaults
import { createServer } from "node:http";

// Optional upstream latency (ms) so in-flight requests genuinely overlap —
// lets the concurrency-cap E2E be deterministic instead of racing a ~1ms reply.
const DELAY = Number(process.env.MOCK_DELAY_MS ?? 0);

const state = {
  fail500Times: 0,
  hangMs: 0, // one-shot
  streamChunks: 8,
  streamDelayMs: 120,
};

const USAGE = { prompt_tokens: 12, completion_tokens: 7, total_tokens: 19 };

function completionBody(model) {
  return {
    id: "chatcmpl-mock",
    object: "chat.completion",
    created: 1,
    model: model || "mock",
    choices: [
      {
        index: 0,
        message: { role: "assistant", content: "Hello from the mock provider." },
        finish_reason: "stop",
      },
    ],
    usage: USAGE,
  };
}

function streamResponse(res, model) {
  res.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
  });
  const chunk = (delta, extra = {}) =>
    `data: ${JSON.stringify({
      id: "chatcmpl-mock",
      object: "chat.completion.chunk",
      created: 1,
      model: model || "mock",
      choices: [{ index: 0, delta, finish_reason: null }],
      ...extra,
    })}\n\n`;
  let i = 0;
  const n = state.streamChunks;
  const timer = setInterval(() => {
    if (res.destroyed) {
      clearInterval(timer);
      return;
    }
    if (i < n) {
      res.write(chunk({ content: `token-${i} ` }));
      i++;
      return;
    }
    clearInterval(timer);
    res.write(chunk({}, { usage: USAGE }));
    res.write("data: [DONE]\n\n");
    res.end();
  }, state.streamDelayMs);
}

createServer((req, res) => {
  const url = req.url ?? "";
  if (req.method === "POST" && url.includes("/__control")) {
    let b = "";
    req.on("data", (d) => (b += d));
    req.on("end", () => {
      const body = JSON.parse(b || "{}");
      state.fail500Times = body.fail500Times ?? 0;
      state.hangMs = body.hangMs ?? 0;
      state.streamChunks = body.streamChunks ?? 8;
      state.streamDelayMs = body.streamDelayMs ?? 120;
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(state));
    });
  } else if (req.method === "POST" && url.includes("/chat/completions")) {
    let b = "";
    req.on("data", (d) => (b += d));
    req.on("end", () => {
      const body = JSON.parse(b || "{}");
      const send = () => {
        // client gave up (timeout test) — the response socket is gone
        if (res.destroyed || res.writableEnded) return;
        if (state.fail500Times > 0) {
          state.fail500Times--;
          res.writeHead(500, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: { message: "mock upstream boom" } }));
          return;
        }
        if (body.stream === true) {
          streamResponse(res, body.model);
          return;
        }
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify(completionBody(body.model)));
      };
      const hang = state.hangMs;
      state.hangMs = 0; // one-shot
      const wait = hang > 0 ? hang : DELAY;
      if (wait > 0) setTimeout(send, wait);
      else send();
    });
  } else if (url.includes("/models")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ object: "list", data: [{ id: "gpt-4o-mini" }] }));
  } else {
    res.writeHead(404);
    res.end("{}");
  }
}).listen(9099, () => console.log("mock provider on :9099"));
