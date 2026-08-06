import assert from 'node:assert/strict'
import test from 'node:test'
import { shouldRedirectUnauthorized } from './authRedirectPolicy.js'

test('shouldRedirectUnauthorized ignores login 401 errors', () => {
  assert.equal(
    shouldRedirectUnauthorized({
      status: 401,
      url: '/auth/login',
      currentPath: '/auth',
      hasToken: false,
    }),
    false
  )
})

test('shouldRedirectUnauthorized redirects expired authenticated app sessions', () => {
  assert.equal(
    shouldRedirectUnauthorized({
      status: 401,
      url: '/platform/workflows/abc',
      currentPath: '/app/results',
      hasToken: true,
    }),
    true
  )
})

test('shouldRedirectUnauthorized ignores non-401 responses', () => {
  assert.equal(
    shouldRedirectUnauthorized({
      status: 500,
      url: '/platform/workflows/abc',
      currentPath: '/app/results',
      hasToken: true,
    }),
    false
  )
})
