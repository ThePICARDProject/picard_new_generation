import assert from 'node:assert/strict'
import test from 'node:test'

import { extractErrorMessage } from './api.js'

test('extractErrorMessage does not expose an HTML error document', () => {
  const fallback = 'Request failed with status 500.'
  const html = '<!doctype html><html><title>Server Error (500)</title></html>'

  assert.equal(extractErrorMessage(html, fallback), fallback)
})

test('extractErrorMessage preserves useful API errors', () => {
  assert.equal(
    extractErrorMessage({ error: 'Execution service unavailable.' }, 'Request failed.'),
    'Execution service unavailable.',
  )
})
