// apps/frontend/src/lib/code-snippets.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  renderClaudeCode,
  renderCurl,
  renderPython,
  renderSnippets,
  renderTypeScript,
} from './code-snippets'
import type { SnippetContext } from './gateway-types'

const ctx: SnippetContext = {
  endpoint: 'openai_chat',
  baseUrl: 'https://gateway.example.com/',
  apiKey: 'sk-test-123',
  model: 'claude-sonnet-4-6',
}

test('renderSnippets emits four langs', () => {
  const snips = renderSnippets(ctx)
  assert.equal(snips.length, 4)
  assert.deepEqual(
    snips.map((s) => s.lang),
    ['curl', 'python', 'typescript', 'claude_code'],
  )
})

test('renderCurl strips trailing slash, includes key + path', () => {
  const out = renderCurl(ctx)
  assert.match(out, /gateway\.example\.com\/v1\/chat\/completions/)
  assert.ok(!out.includes('example.com//v1'), 'no double slash')
  assert.match(out, /Authorization: Bearer sk-test-123/)
  assert.match(out, /claude-sonnet-4-6/)
})

test('renderPython picks SDK per endpoint', () => {
  assert.match(renderPython(ctx), /from openai import OpenAI/)
  assert.match(
    renderPython({ ...ctx, endpoint: 'anthropic_messages' }),
    /from anthropic import Anthropic/,
  )
  assert.match(
    renderPython({ ...ctx, endpoint: 'bedrock_converse' }),
    /import httpx/,
  )
})

test('renderTypeScript picks SDK per endpoint', () => {
  assert.match(renderTypeScript(ctx), /import OpenAI from "openai"/)
  assert.match(
    renderTypeScript({ ...ctx, endpoint: 'anthropic_messages' }),
    /@anthropic-ai\/sdk/,
  )
  assert.match(
    renderTypeScript({ ...ctx, endpoint: 'rerank' }),
    /fetch\(/,
  )
})

test('renderClaudeCode sets ANTHROPIC_BASE_URL + token', () => {
  const out = renderClaudeCode(ctx)
  assert.match(out, /ANTHROPIC_BASE_URL/)
  assert.match(out, /ANTHROPIC_AUTH_TOKEN/)
  assert.match(out, /sk-test-123/)
  assert.ok(!out.includes('example.com/v1'), 'baseUrl trailing slash removed but no /v1 added for Claude Code')
})

test('embeddings vs chat python differ', () => {
  const chat = renderPython(ctx)
  const emb = renderPython({ ...ctx, endpoint: 'openai_embeddings' })
  assert.match(chat, /chat\.completions\.create/)
  assert.match(emb, /embeddings\.create/)
})
