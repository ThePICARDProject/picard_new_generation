import assert from 'node:assert/strict'
import { test } from 'node:test'
import { argumentError, defaultArguments, getArgumentDefinitions } from './argumentDefinitions.js'

test('an unfamiliar algorithm supplies its fields without a name registry', () => {
  const parameters = [
    { name: 'trees', type: 'integer', default: 2, min: 1 },
    { name: 'mode', type: 'choice', default: 'FAST', choices: ['fast', 'accurate'] },
    { name: 'title', type: 'string', default: "A user's model" },
    { name: 'requiredText', type: 'string' },
  ]
  assert.equal(getArgumentDefinitions({ name: 'New classifier', algorithm_config: { parameters } }), parameters)
  assert.deepEqual(defaultArguments(parameters), ['2', 'fast', "A user's model", ''])
  assert.match(argumentError(parameters, defaultArguments(parameters)), /requiredText is required/)
  assert.equal(argumentError(parameters, ['2', 'fast', "A user's model", 'two words']), '')
  assert.equal(getArgumentDefinitions({ name: 'CoDRIFT' }), null)
})

test('numeric validation prevents empty partitions and invalid integer input', () => {
  const fields = [{ name: 'fraction', type: 'number', exclusiveMin: 0, exclusiveMax: 100 }]
  for (const value of ['', '0', '100', 'NaN', 'Infinity']) {
    assert.ok(argumentError(fields, [value]))
  }
  assert.equal(argumentError(fields, ['70.5']), '')
  assert.ok(argumentError([{ name: 'count', type: 'integer' }], ['1.5']))
})

test('a classifier can have no user parameters', () => {
  assert.deepEqual(getArgumentDefinitions({ algorithm_config: { parameters: [] } }), [])
  assert.deepEqual(defaultArguments([]), [])
  assert.equal(argumentError([], []), '')
})
