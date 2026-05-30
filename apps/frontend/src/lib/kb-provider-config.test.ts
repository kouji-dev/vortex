import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  isSelectable,
  resolveSelected,
  selectableIds,
  validateDefaultSelection,
  type ProviderLayer,
} from './kb-provider-config.ts'

function entry(id: string, enabled = true, isDefault = false) {
  return { id, enabled, endpoint: null, has_credential: false, is_default: isDefault }
}

function layer(over: Partial<ProviderLayer> = {}): ProviderLayer {
  return {
    layer: 'vector_stores',
    default_id: 'pgvector',
    items: [entry('pgvector', true, true), entry('qdrant', true), entry('pinecone', false)],
    ...over,
  }
}

test('selectableIds returns only enabled ids', () => {
  assert.deepEqual(selectableIds(layer()), ['pgvector', 'qdrant'])
})

test('selectableIds handles null/empty', () => {
  assert.deepEqual(selectableIds(null), [])
  assert.deepEqual(selectableIds(undefined), [])
})

test('isSelectable true for enabled declared, false for disabled or undeclared', () => {
  assert.equal(isSelectable(layer(), 'pgvector'), true)
  assert.equal(isSelectable(layer(), 'qdrant'), true)
  assert.equal(isSelectable(layer(), 'pinecone'), false) // declared but disabled
  assert.equal(isSelectable(layer(), 'weaviate'), false) // undeclared
})

test('validateDefaultSelection enforces enabled set', () => {
  assert.equal(validateDefaultSelection(layer(), 'pgvector'), null)
  assert.equal(validateDefaultSelection(layer(), ''), 'Selection required')
  assert.match(
    validateDefaultSelection(layer(), 'pinecone') ?? '',
    /not enabled in this deployment/,
  )
  assert.match(
    validateDefaultSelection(layer(), 'weaviate') ?? '',
    /not enabled in this deployment/,
  )
  assert.equal(
    validateDefaultSelection(null, 'pgvector'),
    'Provider layer not configured',
  )
})

test('resolveSelected keeps current when selectable', () => {
  assert.equal(resolveSelected(layer(), 'qdrant'), 'qdrant')
})

test('resolveSelected falls back to default when current invalid', () => {
  assert.equal(resolveSelected(layer(), 'pinecone'), 'pgvector')
  assert.equal(resolveSelected(layer(), null), 'pgvector')
})

test('resolveSelected falls back to first enabled when default disabled', () => {
  const l = layer({
    default_id: 'pinecone',
    items: [entry('pinecone', false, true), entry('qdrant', true)],
  })
  assert.equal(resolveSelected(l, undefined), 'qdrant')
})

test('resolveSelected returns empty when nothing enabled', () => {
  const l = layer({ default_id: null, items: [entry('pinecone', false)] })
  assert.equal(resolveSelected(l, undefined), '')
})
