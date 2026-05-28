import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  capabilityTags,
  filterModels,
  formatPricePerK,
  sortModels,
} from './gateway-models.ts'
import type { ModelInfo } from './gateway-types.ts'

function m(over: Partial<ModelInfo> = {}): ModelInfo {
  return {
    id: 'm' + Math.random(),
    provider: 'anthropic',
    model_id: 'claude-sonnet-4-6',
    display_name: 'Claude Sonnet 4.6',
    capabilities: { streaming: true, tools: true },
    price_input_per_1k_cents: 30,
    price_output_per_1k_cents: 150,
    price_cache_read_per_1k_cents: 3,
    deprecated_at: null,
    ...over,
  }
}

test('formatPricePerK: dollars at $1+ → 2 decimals', () => {
  assert.equal(formatPricePerK(150), '$1.50/1k')
})

test('formatPricePerK: cents at 1c-99c → 3 decimals', () => {
  assert.equal(formatPricePerK(30), '$0.300/1k')
})

test('formatPricePerK: sub-cent → 4 decimals', () => {
  assert.equal(formatPricePerK(0.5), '$0.0050/1k')
})

test('capabilityTags: ordered, only truthy', () => {
  assert.deepEqual(
    capabilityTags({ vision: true, streaming: true, tools: false }),
    ['streaming', 'vision'],
  )
})

test('capabilityTags: undefined → []', () => {
  assert.deepEqual(capabilityTags(undefined), [])
})

test('filterModels: by provider', () => {
  const arr = [m({ provider: 'anthropic' }), m({ provider: 'openai' })]
  assert.equal(filterModels(arr, { provider: 'openai' }).length, 1)
})

test('filterModels: search by model_id', () => {
  const arr = [m({ model_id: 'gpt-4o' }), m({ model_id: 'claude' })]
  assert.equal(filterModels(arr, { search: 'gpt' }).length, 1)
})

test('filterModels: by capability', () => {
  const arr = [
    m({ capabilities: { vision: true } }),
    m({ capabilities: { tools: true } }),
  ]
  assert.equal(filterModels(arr, { capability: 'vision' }).length, 1)
})

test('filterModels: excludes deprecated by default', () => {
  const arr = [m({ deprecated_at: '2026-01-01' }), m()]
  assert.equal(filterModels(arr, {}).length, 1)
  assert.equal(filterModels(arr, { includeDeprecated: true }).length, 2)
})

test('sortModels: provider then model_id', () => {
  const arr = [
    m({ provider: 'openai', model_id: 'gpt-4o' }),
    m({ provider: 'anthropic', model_id: 'claude-opus' }),
    m({ provider: 'anthropic', model_id: 'claude-haiku' }),
  ]
  const sorted = sortModels(arr)
  assert.equal(sorted[0].model_id, 'claude-haiku')
  assert.equal(sorted[1].model_id, 'claude-opus')
  assert.equal(sorted[2].model_id, 'gpt-4o')
})
