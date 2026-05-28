// apps/frontend/src/lib/code-snippets.ts
// Pure builders for code snippets per compatible endpoint (J10).
import type { SnippetContext, SnippetEndpoint, SnippetLang } from './gateway-types'

export interface Snippet {
  lang: SnippetLang
  label: string
  body: string
}

const ENDPOINT_PATH: Record<SnippetEndpoint, string> = {
  openai_chat: '/v1/chat/completions',
  openai_embeddings: '/v1/embeddings',
  anthropic_messages: '/v1/messages',
  bedrock_converse: '/v1/converse',
  rerank: '/v1/rerank',
  moderations: '/v1/moderations',
}

/** Render all four supported langs for the given context. */
export function renderSnippets(ctx: SnippetContext): Snippet[] {
  return [
    { lang: 'curl', label: 'cURL', body: renderCurl(ctx) },
    { lang: 'python', label: 'Python', body: renderPython(ctx) },
    { lang: 'typescript', label: 'TypeScript', body: renderTypeScript(ctx) },
    { lang: 'claude_code', label: 'Claude Code config', body: renderClaudeCode(ctx) },
  ]
}

function url(ctx: SnippetContext): string {
  return stripTrailingSlash(ctx.baseUrl) + ENDPOINT_PATH[ctx.endpoint]
}

function stripTrailingSlash(s: string): string {
  return s.endsWith('/') ? s.slice(0, -1) : s
}

/** Public for tests. */
export function renderCurl(ctx: SnippetContext): string {
  const body = sampleBody(ctx)
  return [
    `curl ${url(ctx)} \\`,
    `  -H "Authorization: Bearer ${ctx.apiKey}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${JSON.stringify(body)}'`,
  ].join('\n')
}

export function renderPython(ctx: SnippetContext): string {
  if (ctx.endpoint === 'openai_chat' || ctx.endpoint === 'openai_embeddings') {
    return [
      `from openai import OpenAI`,
      `client = OpenAI(base_url="${stripTrailingSlash(ctx.baseUrl)}/v1", api_key="${ctx.apiKey}")`,
      ``,
      ctx.endpoint === 'openai_chat'
        ? `resp = client.chat.completions.create(\n    model="${ctx.model}",\n    messages=[{"role": "user", "content": "Hello"}],\n)\nprint(resp.choices[0].message.content)`
        : `resp = client.embeddings.create(model="${ctx.model}", input="Hello")\nprint(resp.data[0].embedding[:8])`,
    ].join('\n')
  }
  if (ctx.endpoint === 'anthropic_messages') {
    return [
      `from anthropic import Anthropic`,
      `client = Anthropic(base_url="${stripTrailingSlash(ctx.baseUrl)}", api_key="${ctx.apiKey}")`,
      ``,
      `msg = client.messages.create(`,
      `    model="${ctx.model}",`,
      `    max_tokens=1024,`,
      `    messages=[{"role": "user", "content": "Hello"}],`,
      `)`,
      `print(msg.content[0].text)`,
    ].join('\n')
  }
  // Generic httpx fallback (bedrock, rerank, moderations)
  return [
    `import httpx`,
    `r = httpx.post(`,
    `    "${url(ctx)}",`,
    `    headers={"Authorization": "Bearer ${ctx.apiKey}"},`,
    `    json=${JSON.stringify(sampleBody(ctx))},`,
    `)`,
    `print(r.json())`,
  ].join('\n')
}

export function renderTypeScript(ctx: SnippetContext): string {
  if (ctx.endpoint === 'openai_chat' || ctx.endpoint === 'openai_embeddings') {
    return [
      `import OpenAI from "openai"`,
      `const client = new OpenAI({ baseURL: "${stripTrailingSlash(ctx.baseUrl)}/v1", apiKey: "${ctx.apiKey}" })`,
      ``,
      ctx.endpoint === 'openai_chat'
        ? `const resp = await client.chat.completions.create({\n  model: "${ctx.model}",\n  messages: [{ role: "user", content: "Hello" }],\n})\nconsole.log(resp.choices[0].message.content)`
        : `const resp = await client.embeddings.create({ model: "${ctx.model}", input: "Hello" })\nconsole.log(resp.data[0].embedding.slice(0, 8))`,
    ].join('\n')
  }
  if (ctx.endpoint === 'anthropic_messages') {
    return [
      `import Anthropic from "@anthropic-ai/sdk"`,
      `const client = new Anthropic({ baseURL: "${stripTrailingSlash(ctx.baseUrl)}", apiKey: "${ctx.apiKey}" })`,
      ``,
      `const msg = await client.messages.create({`,
      `  model: "${ctx.model}",`,
      `  max_tokens: 1024,`,
      `  messages: [{ role: "user", content: "Hello" }],`,
      `})`,
      `console.log(msg.content)`,
    ].join('\n')
  }
  // Generic fetch
  return [
    `const res = await fetch("${url(ctx)}", {`,
    `  method: "POST",`,
    `  headers: {`,
    `    "Authorization": "Bearer ${ctx.apiKey}",`,
    `    "Content-Type": "application/json",`,
    `  },`,
    `  body: JSON.stringify(${JSON.stringify(sampleBody(ctx))}),`,
    `})`,
    `console.log(await res.json())`,
  ].join('\n')
}

/** Claude Code uses ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN. */
export function renderClaudeCode(ctx: SnippetContext): string {
  return [
    `# ~/.claude/settings.json or env vars`,
    `{`,
    `  "env": {`,
    `    "ANTHROPIC_BASE_URL": "${stripTrailingSlash(ctx.baseUrl)}",`,
    `    "ANTHROPIC_AUTH_TOKEN": "${ctx.apiKey}",`,
    `    "ANTHROPIC_MODEL": "${ctx.model}"`,
    `  }`,
    `}`,
    ``,
    `# Or shell:`,
    `export ANTHROPIC_BASE_URL=${stripTrailingSlash(ctx.baseUrl)}`,
    `export ANTHROPIC_AUTH_TOKEN=${ctx.apiKey}`,
    `claude "Hello"`,
  ].join('\n')
}

function sampleBody(ctx: SnippetContext): Record<string, unknown> {
  switch (ctx.endpoint) {
    case 'openai_chat':
      return { model: ctx.model, messages: [{ role: 'user', content: 'Hello' }] }
    case 'openai_embeddings':
      return { model: ctx.model, input: 'Hello' }
    case 'anthropic_messages':
      return {
        model: ctx.model,
        max_tokens: 1024,
        messages: [{ role: 'user', content: 'Hello' }],
      }
    case 'bedrock_converse':
      return {
        modelId: ctx.model,
        messages: [{ role: 'user', content: [{ text: 'Hello' }] }],
      }
    case 'rerank':
      return { model: ctx.model, query: 'apple', documents: ['fruit', 'car'] }
    case 'moderations':
      return { model: ctx.model, input: 'Hello' }
  }
}
