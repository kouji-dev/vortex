import { describe, expect, it } from 'vitest'

import {
  collectAllTags,
  filterByTags,
  formatTags,
  parseTagsInput,
  toggleTag,
} from './kb-tags'

describe('parseTagsInput', () => {
  it('returns [] for empty input', () => {
    expect(parseTagsInput('')).toEqual([])
    expect(parseTagsInput('   ')).toEqual([])
  })

  it('splits + trims + lowercases', () => {
    expect(parseTagsInput('Alpha, Beta, gamma')).toEqual(['alpha', 'beta', 'gamma'])
  })

  it('dedupes case-insensitively', () => {
    expect(parseTagsInput('alpha, ALPHA, alpha')).toEqual(['alpha'])
  })

  it('drops empty pieces', () => {
    expect(parseTagsInput('alpha,,,beta')).toEqual(['alpha', 'beta'])
  })
})

describe('formatTags', () => {
  it('joins with comma+space', () => {
    expect(formatTags(['a', 'b', 'c'])).toBe('a, b, c')
  })

  it('handles null/empty', () => {
    expect(formatTags(null)).toBe('')
    expect(formatTags(undefined)).toBe('')
    expect(formatTags([])).toBe('')
  })
})

describe('collectAllTags', () => {
  it('returns sorted unique set across kbs', () => {
    const kbs = [
      { tags: ['gamma', 'alpha'] },
      { tags: ['beta', 'ALPHA'] },
      { tags: null },
      {},
    ]
    expect(collectAllTags(kbs)).toEqual(['alpha', 'beta', 'gamma'])
  })

  it('ignores blanks', () => {
    expect(collectAllTags([{ tags: ['  ', ''] }])).toEqual([])
  })
})

describe('toggleTag', () => {
  it('adds when missing', () => {
    expect(toggleTag(['a'], 'b')).toEqual(['a', 'b'])
  })

  it('removes when present', () => {
    expect(toggleTag(['a', 'b'], 'a')).toEqual(['b'])
  })

  it('matches case-insensitively', () => {
    expect(toggleTag(['a'], 'A')).toEqual([])
  })

  it('ignores blank input', () => {
    expect(toggleTag(['a'], '   ')).toEqual(['a'])
  })
})

describe('filterByTags', () => {
  const items = [
    { id: 1, tags: ['alpha', 'beta'] },
    { id: 2, tags: ['beta'] },
    { id: 3, tags: ['gamma'] },
    { id: 4 },
  ]

  it('keeps everything for empty filter', () => {
    expect(filterByTags(items, []).map((i) => i.id)).toEqual([1, 2, 3, 4])
  })

  it('AND-matches every active tag', () => {
    expect(filterByTags(items, ['alpha']).map((i) => i.id)).toEqual([1])
    expect(filterByTags(items, ['beta']).map((i) => i.id)).toEqual([1, 2])
    expect(filterByTags(items, ['alpha', 'beta']).map((i) => i.id)).toEqual([1])
    expect(filterByTags(items, ['alpha', 'gamma'])).toEqual([])
  })

  it('case-insensitive match', () => {
    expect(filterByTags(items, ['ALPHA']).map((i) => i.id)).toEqual([1])
  })
})
