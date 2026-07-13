// Multi-envelope fake provider for E2E. The gateway is pointed here per host via
// *_BASE_URL env vars. Speaks OpenAI Chat, Anthropic Messages, Bedrock invoke,
// and Azure-deployment paths, and records the last upstream request so tests can
// assert envelope-by-family + model-id translation.
//
// Test controls (POST /__control JSON):
//   { fail500Times: N }  → the next N POST requests answer 500
//   { hangMs: N }        → the next ONE POST request stalls N ms before replying
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

// Last upstream request seen (path/body/model), for assertions via GET /__last.
let last = null;

function openaiCompletion(model) {
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

function anthropicMessage(model, body) {
  // If the client sent tools, answer with a tool_use block (proves tool
  // definitions survive the passthrough in both directions).
  const content = [{ type: "text", text: "Hello from the mock provider." }];
  let stop = "end_turn";
  if (Array.isArray(body?.tools) && body.tools.length) {
    content.push({
      type: "tool_use",
      id: "toolu_mock",
      name: body.tools[0].name ?? "tool",
      input: { ok: true },
    });
    stop = "tool_use";
  }
  return {
    id: "msg_mock",
    type: "message",
    role: "assistant",
    model: model || "mock",
    content,
    stop_reason: stop,
    stop_sequence: null,
    usage: { input_tokens: 12, output_tokens: 7 },
  };
}

function responsesObject(model, body) {
  const output = [
    {
      type: "message",
      id: "msg_mock",
      status: "completed",
      role: "assistant",
      content: [{ type: "output_text", text: "Hello from the mock provider.", annotations: [] }],
    },
  ];
  if (Array.isArray(body?.tools) && body.tools.length) {
    output.push({
      type: "function_call",
      id: "fc_mock",
      call_id: "call_mock",
      name: body.tools[0].name ?? "tool",
      arguments: "{}",
      status: "completed",
    });
  }
  return {
    id: "resp_mock",
    object: "response",
    created_at: 1,
    status: "completed",
    model: model || "mock",
    output,
    output_text: "Hello from the mock provider.",
    usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
  };
}

createServer((req, res) => {
  const url = req.url ?? "";
  const method = req.method ?? "GET";

  if (method === "POST" && url.includes("/__control")) {
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
    return;
  }

  if (method === "GET" && url.startsWith("/__last")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(last ?? {}));
    return;
  }

  if (method === "GET" && url.includes("/models")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ object: "list", data: [{ id: "gpt-4o-mini" }] }));
    return;
  }

  if (method === "POST") {
    let b = "";
    req.on("data", (d) => (b += d));
    req.on("end", () => {
      const body = JSON.parse(b || "{}");

      const answer = () => {
        // client gave up (timeout test) — the response socket is gone
        if (res.destroyed || res.writableEnded) return;
        if (state.fail500Times > 0) {
          state.fail500Times--;
          res.writeHead(500, { "content-type": "application/json" });
          res.end(JSON.stringify({ error: { message: "mock upstream boom" } }));
          return;
        }

        const json = (obj) => {
          res.writeHead(200, { "content-type": "application/json" });
          res.end(JSON.stringify(obj));
        };

        // Bedrock native invoke: POST /model/{id}/invoke — id is in the URL.
        const bedrock = url.match(/\/model\/([^/]+)\/invoke/);
        if (bedrock) {
          const upstreamId = decodeURIComponent(bedrock[1]);
          last = { path: url, envelope: "anthropic-bedrock", model: upstreamId, body };
          json(anthropicMessage(upstreamId, body));
          return;
        }

        // OpenAI Responses (Codex).
        if (url.includes("/responses")) {
          last = { path: url, envelope: "responses", model: body.model, body };
          json(responsesObject(body.model, body));
          return;
        }

        // Anthropic Messages (direct or Vertex rawPredict).
        if (url.includes("/v1/messages") || url.includes(":rawPredict")) {
          last = { path: url, envelope: "anthropic", model: body.model, body };
          json(anthropicMessage(body.model, body));
          return;
        }

        // Gemini generateContent.
        if (url.includes(":generateContent")) {
          last = { path: url, envelope: "google", model: null, body };
          json({
            candidates: [
              { content: { parts: [{ text: "Hello from the mock provider." }] } },
            ],
            usageMetadata: { promptTokenCount: 12, candidatesTokenCount: 7, totalTokenCount: 19 },
          });
          return;
        }

        if (url.includes("/embeddings")) {
          last = { path: url, envelope: "openai-embeddings", model: body.model, body };
          json({
            object: "list",
            data: [{ object: "embedding", index: 0, embedding: [0.1, 0.2, 0.3] }],
            model: body.model,
            usage: { prompt_tokens: 5, total_tokens: 5 },
          });
          return;
        }

        // OpenAI Chat (direct or Azure deployment path) — the default.
        last = { path: url, envelope: "openai", model: body.model, body };
        if (body.stream === true) {
          streamResponse(res, body.model);
          return;
        }
        json(openaiCompletion(body.model));
      };

      const hang = state.hangMs;
      state.hangMs = 0; // one-shot
      const wait = hang > 0 ? hang : DELAY;
      if (wait > 0) setTimeout(answer, wait);
      else answer();
    });
    return;
  }

  res.writeHead(404);
  res.end("{}");
}).listen(Number(process.env.MOCK_PORT) || 9099, () =>
  console.log(`mock provider on :${Number(process.env.MOCK_PORT) || 9099}`),
);
