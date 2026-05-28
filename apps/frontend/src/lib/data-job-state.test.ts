import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import {
  DELETE_CONFIRMATION_PHRASE,
  deleteConfirmed,
  describeDeleteScope,
  isTerminal,
  jobStateClass,
  summarizeDelete,
  summarizeExport,
} from './data-job-state.ts'
import type { DataDeleteJob, DataExportJob } from './admin-types.ts'

test('jobStateClass: known statuses pass through', () => {
  assert.equal(jobStateClass('pending'), 'pending')
  assert.equal(jobStateClass('running'), 'running')
  assert.equal(jobStateClass('completed'), 'completed')
  assert.equal(jobStateClass('failed'), 'failed')
})

test('jobStateClass: unknown → "unknown"', () => {
  assert.equal(jobStateClass('weird'), 'unknown')
})

test('isTerminal: only completed + failed', () => {
  assert.equal(isTerminal('completed'), true)
  assert.equal(isTerminal('failed'), true)
  assert.equal(isTerminal('pending'), false)
  assert.equal(isTerminal('running'), false)
})

test('describeDeleteScope: org subject', () => {
  assert.equal(describeDeleteScope({ subject: 'org' }), 'all data in this organisation')
})

test('describeDeleteScope: user subject with id', () => {
  assert.equal(describeDeleteScope({ subject: 'user', user_id: 42 }), 'data for user 42')
})

test('describeDeleteScope: user without id', () => {
  assert.equal(describeDeleteScope({ subject: 'user' }), 'data for user (unknown)')
})

test('describeDeleteScope: unknown subject → JSON', () => {
  const out = describeDeleteScope({ subject: 'team', team_id: 'abc' })
  assert.ok(out.startsWith('scope '))
  assert.ok(out.includes('team'))
})

test('deleteConfirmed: exact match (case-insensitive, trim)', () => {
  assert.equal(deleteConfirmed(DELETE_CONFIRMATION_PHRASE), true)
  assert.equal(deleteConfirmed('  DELETE my data  '), true)
})

test('deleteConfirmed: wrong text rejected', () => {
  assert.equal(deleteConfirmed('delete'), false)
  assert.equal(deleteConfirmed(''), false)
})

test('summarizeExport: pulls relevant fields', () => {
  const job: DataExportJob = {
    id: 'j1',
    org_id: 'o1',
    requested_by: 5,
    status: 'pending',
    result_url: null,
    requested_at: '2025-01-01T00:00:00Z',
    completed_at: null,
  }
  const s = summarizeExport(job)
  assert.equal(s.id, 'j1')
  assert.equal(s.status, 'pending')
  assert.equal(s.resultUrl, null)
})

test('summarizeDelete: includes scope label', () => {
  const job: DataDeleteJob = {
    id: 'j2',
    org_id: 'o1',
    scope_json: { subject: 'org', org_id: 'o1' },
    status: 'running',
    requested_at: '2025-01-01T00:00:00Z',
    completed_at: null,
  }
  const s = summarizeDelete(job)
  assert.ok(s.scopeLabel?.includes('all data'))
})
