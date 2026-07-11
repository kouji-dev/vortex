// Multi-envelope fake provider for E2E. The gateway is pointed here per host via
// *_BASE_URL env vars. Speaks OpenAI Chat, Anthropic Messages, Bedrock invoke,
// and Azure-deployment paths, and records the last upstream request so tests can
// assert envelope-by-family + model-id translation.
import { createServer } from "node:http";

// Optional upstream latency (ms) so in-flight requests genuinely overlap —
// lets the concurrency-cap E2E be deterministic instead of racing a ~1ms reply.
const DELAY = Number(process.env.MOCK_DELAY_MS ?? 0);

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
    usage: { prompt_tokens: 12, completion_tokens: 7, total_tokens: 19 },
  };
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

function send(res, obj) {
  const done = () => {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  if (DELAY > 0) setTimeout(done, DELAY);
  else done();
}

createServer((req, res) => {
  const url = req.url ?? "";
  const method = req.method ?? "GET";

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

      // Bedrock native invoke: POST /model/{id}/invoke — id is in the URL.
      const bedrock = url.match(/\/model\/([^/]+)\/invoke/);
      if (bedrock) {
        const upstreamId = decodeURIComponent(bedrock[1]);
        last = { path: url, envelope: "anthropic-bedrock", model: upstreamId, body };
        send(res, anthropicMessage(upstreamId));
        return;
      }

      // OpenAI Responses (Codex).
      if (url.includes("/responses")) {
        last = { path: url, envelope: "responses", model: body.model, body };
        send(res, responsesObject(body.model, body));
        return;
      }

      // Anthropic Messages (direct or Vertex rawPredict).
      if (url.includes("/v1/messages") || url.includes(":rawPredict")) {
        last = { path: url, envelope: "anthropic", model: body.model, body };
        send(res, anthropicMessage(body.model, body));
        return;
      }

      // Gemini generateContent.
      if (url.includes(":generateContent")) {
        last = { path: url, envelope: "google", model: null, body };
        send(res, {
          candidates: [
            { content: { parts: [{ text: "Hello from the mock provider." }] } },
          ],
          usageMetadata: { promptTokenCount: 12, candidatesTokenCount: 7, totalTokenCount: 19 },
        });
        return;
      }

      if (url.includes("/embeddings")) {
        last = { path: url, envelope: "openai-embeddings", model: body.model, body };
        send(res, {
          object: "list",
          data: [{ object: "embedding", index: 0, embedding: [0.1, 0.2, 0.3] }],
          model: body.model,
          usage: { prompt_tokens: 5, total_tokens: 5 },
        });
        return;
      }

      // OpenAI Chat (direct or Azure deployment path) — the default.
      last = { path: url, envelope: "openai", model: body.model, body };
      send(res, openaiCompletion(body.model));
    });
    return;
  }

  res.writeHead(404);
  res.end("{}");
}).listen(Number(process.env.MOCK_PORT) || 9099, () =>
  console.log(`mock provider on :${Number(process.env.MOCK_PORT) || 9099}`),
);
