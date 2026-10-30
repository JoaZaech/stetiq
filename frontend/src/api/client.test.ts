import { describe, expect, it } from 'vitest'
import { ApiError, errorTitle, isAccessDenied, isNotFound } from './client'

const notFound = new ApiError(404, 'NotFoundError', "Knowledge Graph 'nope' does not exist")
const denied = new ApiError(
  403,
  'PermissionDeniedError',
  "Token t1 (user 'grace') lacks edit permission on Knowledge Graph 'support'",
)
const broken = new ApiError(500, 'HttpError', '500 Internal Server Error')

describe('isNotFound (reads)', () => {
  it('reads an unknown id and a Knowledge Graph outside the grants alike', () => {
    expect(isNotFound(notFound)).toBe(true)
    expect(isNotFound(denied)).toBe(true)
  })

  it('is false for any other failure', () => {
    expect(isNotFound(broken)).toBe(false)
    expect(isNotFound(new Error('offline'))).toBe(false)
  })
})

describe('a refused write', () => {
  it('is an access error', () => {
    expect(isAccessDenied(denied)).toBe(true)
    expect(isAccessDenied(notFound)).toBe(false)
    expect(isAccessDenied(broken)).toBe(false)
  })

  it('is titled as an access error, never as not found', () => {
    expect(errorTitle(denied, 'Could not promote')).toBe('Access denied')
    expect(errorTitle(denied, 'Could not promote')).not.toMatch(/not found/i)
    expect(errorTitle(notFound, 'Could not promote')).toBe('Could not promote')
    expect(errorTitle(broken, 'Could not promote')).toBe('Could not promote')
  })
})
