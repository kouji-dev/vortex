import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  memoryIdsFromMessage,
  sourceConversationIdFromMessage,
} from './memory-message-refs.ts'

test('memoryIdsFromMessage: null / undefined → []', () => {
  assert.deepEqual(memoryIdsFromMessage(null), [])
  assert.deepEqual(memoryIdsFromMessage(undefined), [])
  assert.deepEqual(memoryIdsFromMessage(42), [])
})

test('memoryIdsFromMessage: no data → []', () => {
  assert.deepEqual(memoryIdsFromMessage({}), [])
  assert.deepEqual(memoryIdsFromMessage({ data: null }), [])
})

test('memoryIdsFromMessage: extracts strings only', () => {
  const msg = { data: { memory_ids: ['a', 1, null, 'b'] } }
  assert.deepEqual(memoryIdsFromMessage(msg), ['a', 'b'])
})

test('memoryIdsFromMessage: ids not array → []', () => {
  const msg = { data: { memory_ids: 'a,b' } }
  assert.deepEqual(memoryIdsFromMessage(msg), [])
})

test('sourceConversationIdFromMessage: handles string + number + missing', () => {
  assert.equal(sourceConversationIdFromMessage({ conversation_id: 'c-1' }), 'c-1')
  assert.equal(sourceConversationIdFromMessage({ conversation_id: 42 }), '42')
  assert.equal(sourceConversationIdFromMessage({}), null)
  assert.equal(sourceConversationIdFromMessage(null), null)
})
