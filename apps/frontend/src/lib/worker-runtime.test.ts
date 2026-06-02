import { test } from 'node:test'
import assert from 'node:assert/strict'
import { inferRuntime } from './worker-runtime.ts'

test('inferRuntime maps claude + codex models', () => {
  assert.equal(inferRuntime('claude-opus-4-7'), 'claude')
  assert.equal(inferRuntime('gpt-5.4-codex'), 'codex')
  assert.equal(inferRuntime('gemini-3.1-pro'), null)
})
