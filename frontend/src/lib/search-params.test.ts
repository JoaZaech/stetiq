import { describe, expect, it } from 'vitest'
import { setOrDeleteParam } from './search-params'

describe('setOrDeleteParam', () => {
  it('sets a param, keeping the others', () => {
    expect(setOrDeleteParam(new URLSearchParams('view=table'), 'q', 'trip').toString()).toBe('view=table&q=trip')
    expect(setOrDeleteParam(new URLSearchParams('q=bus'), 'q', 'trip').toString()).toBe('q=trip')
  })

  it('deletes a param set to nothing or the empty string', () => {
    expect(setOrDeleteParam(new URLSearchParams('q=trip&view=table'), 'q', '').toString()).toBe('view=table')
    expect(setOrDeleteParam(new URLSearchParams('q=trip'), 'q', null).toString()).toBe('')
    expect(setOrDeleteParam(new URLSearchParams('q=trip'), 'q', undefined).toString()).toBe('')
  })
})
