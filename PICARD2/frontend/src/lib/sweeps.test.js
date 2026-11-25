import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { buildSweepPlan, candidateValues, initialConfiguration, sweepCounts, sweepStatus } from '../features/sweeps/sweepModel.js'
import { createApiSweepRepository, describeError, fromApiSweep, toDefinition } from '../features/sweeps/sweepApi.js'

const manifest = JSON.parse(readFileSync(new URL('../../../backend/scripts/manifests/codrift.json', import.meta.url), 'utf8'))
const definitions = manifest.parameters
function draft() {
  const configuration = initialConfiguration(definitions)
  configuration.numTrees = { ...configuration.numTrees, vary: true, candidates: '10, 20, 30' }
  configuration.maxDepth = { ...configuration.maxDepth, vary: true, candidates: '5, 10' }
  configuration.impurity = { ...configuration.impurity, vary: true, selected: ['gini', 'entropy'] }
  return { name: 'CoDRIFT Hyperparameter Test', algorithm: { id: 'codrift', name: 'CoDRIFT', algorithm_config: manifest }, dataset: { id: 'sample', name: 'Sample dataset' }, configuration }
}
function batch(statuses, requested = false) {
  return { cancel_requested: requested, experiments: statuses.map((status, index) => ({ id: String(index), status })) }
}

test('Cartesian product is 3 × 2 × 2 = 12, unique, ordered, and preserves fixed defaults', () => {
  const plan = buildSweepPlan(definitions, draft().configuration)
  assert.equal(plan.error, '')
  assert.equal(plan.count, 12)
  assert.equal(new Set(plan.combinations.map((row) => JSON.stringify(row))).size, 12)
  assert.deepEqual(plan.varied.map((axis) => axis.values.length), [3, 2, 2])
  assert.deepEqual(plan.combinations[0], { numClasses: 2, numTrees: 10, impurity: 'gini', maxDepth: 5, maxBins: 32, percentLabeled: 70, k: 1 })
  assert.equal(plan.combinations[11].numTrees, 30)
  assert.equal(plan.combinations[11].impurity, 'entropy')
  assert.equal(plan.combinations[11].maxDepth, 10)
})

test('standard configuration validates fixed values even when saved candidates are invalid', () => {
  const configuration = draft().configuration
  configuration.numTrees.candidates = 'invalid'
  const fixedPlan = buildSweepPlan(definitions, configuration, { varyParameters: false })
  assert.equal(fixedPlan.error, '')
  assert.equal(fixedPlan.count, 1)
  assert.deepEqual(fixedPlan.varied, [])
  configuration.numTrees.value = '0'
  assert.ok(buildSweepPlan(definitions, configuration, { varyParameters: false }).errors.numTrees)
  assert.ok(buildSweepPlan(definitions, configuration).errors.numTrees)
})

test('numeric ranges include reachable endpoints without floating point noise', () => {
  const parameter = { name: 'fraction', type: 'number', min: 0, max: 1 }
  assert.deepEqual(candidateValues(parameter, { vary: true, mode: 'range', start: '0.1', end: '0.3', step: '0.1' }), [0.1, 0.2, 0.3])
  assert.deepEqual(candidateValues(parameter, { vary: true, mode: 'range', start: '0', end: '0.5', step: '0.2' }), [0, 0.2, 0.4])
  for (const patch of [{ step: '0' }, { step: '-1' }, { start: '' }, { end: '-1' }, { end: 'Infinity' }, { end: '2' }, { step: '0.00001' }]) {
    assert.throws(() => candidateValues(parameter, { vary: true, mode: 'range', start: '0', end: '1', step: '0.1', ...patch }))
  }
  assert.throws(() => candidateValues({ name: 'trees', type: 'integer' }, { vary: true, mode: 'range', start: '1', end: '3', step: '.5' }))
})

test('validation rejects empty selections, invalid choices, numeric bounds, and excessive products', () => {
  const values = draft().configuration
  values.impurity.selected = []
  assert.ok(buildSweepPlan(definitions, values).errors.impurity)
  values.impurity.selected = ['bogus']
  assert.ok(buildSweepPlan(definitions, values).errors.impurity)
  values.impurity.selected = ['gini', 'entropy']
  values.numTrees.candidates = '10, '
  assert.ok(buildSweepPlan(definitions, values).errors.numTrees)
  values.numTrees.candidates = '1.5'
  assert.ok(buildSweepPlan(definitions, values).errors.numTrees)
  values.numTrees.candidates = 'NaN'
  assert.ok(buildSweepPlan(definitions, values).errors.numTrees)
  values.numTrees.candidates = '0'
  assert.ok(buildSweepPlan(definitions, values).errors.numTrees)
  values.numTrees = { ...values.numTrees, mode: 'range', start: '1', end: '100', step: '1' }
  const plan = buildSweepPlan(definitions, values)
  assert.equal(plan.count, 400)
  assert.match(plan.error, /100 or fewer/)
  assert.equal(plan.combinations.length, 0)
  assert.ok(buildSweepPlan(definitions, initialConfiguration(definitions)).error)
})

test('unfamiliar string parameters preserve spaces and numeric duplicates count once', () => {
  const fields = [{ name: 'modelName', type: 'string', default: 'My first model' }, { name: 'rate', type: 'number', default: 0.1 }]
  const configuration = initialConfiguration(fields)
  configuration.modelName = { ...configuration.modelName, vary: true, candidates: 'My first model\nAnother model' }
  configuration.rate = { ...configuration.rate, vary: true, candidates: '0.1, 0.10, 0.2' }
  const plan = buildSweepPlan(fields, configuration)
  assert.equal(plan.count, 4)
  assert.equal(plan.combinations[0].modelName, 'My first model')
  assert.deepEqual(plan.axes[1].values, [0.1, 0.2])
})

test('batch statuses follow the specified precedence, including cancellation drain', () => {
  assert.equal(sweepStatus(batch(['Running', 'Cancelled'], true)), 'Running')
  assert.equal(sweepStatus(batch(['Queued', 'Failed'])), 'Queued')
  assert.equal(sweepStatus(batch(['Pending', 'Cancelled'], true)), 'Queued')
  assert.equal(sweepStatus(batch(['Success', 'Cancelled', 'Failed'], true)), 'Cancelled')
  assert.equal(sweepStatus(batch(['Success', 'Success'])), 'Success')
  assert.equal(sweepStatus(batch(['Success', 'Failed'])), 'Completed with failures')
  assert.equal(sweepStatus(batch(['Success'], true)), 'Success')
})

test('progress counts failures as completed and cancellation as settled', () => {
  const counts = sweepCounts(batch(['Success', 'Failed', 'Cancelled', 'Running', 'Queued']))
  assert.equal(counts.completed, 2)
  assert.equal(counts.settled, 3)
  assert.equal(counts.progress, 60)
})

test('server counts and status take precedence over the run table', () => {
  const sweep = { status: 'Running', counts: { Success: 1, Running: 1, Queued: 2 }, experiments: [] }
  assert.equal(sweepStatus(sweep), 'Running')
  assert.deepEqual([sweepCounts(sweep).total, sweepCounts(sweep).settled], [4, 1])
})

test('form state becomes the API definition: fixed values, lists, choices and ranges', () => {
  const configuration = draft().configuration
  configuration.maxBins = { ...configuration.maxBins, vary: true, mode: 'range', start: '16', end: '64', step: '16' }
  const swept = toDefinition(definitions, configuration, true)
  assert.deepEqual(swept.numTrees, ['10', '20', '30'])
  assert.deepEqual(swept.impurity, ['gini', 'entropy'])
  assert.deepEqual(swept.maxBins, { start: '16', stop: '64', step: '16' })
  assert.equal(swept.numClasses, '2')
  // With the sweep option off, every parameter sends its single fixed value.
  const single = toDefinition(definitions, configuration, false)
  assert.equal(Object.values(single).every((value) => typeof value === 'string'), true)
})

function fakeServer(routes) {
  const calls = []
  const request = async (path, options = {}) => {
    calls.push({ path, ...options })
    const handler = routes[`${options.method || 'GET'} ${path}`]
    if (!handler) throw Object.assign(new Error('Not found'), { status: 404 })
    return handler(options)
  }
  return { calls, request }
}
const apiSweep = (id, extra = {}) => ({
  id, name: `Sweep ${id}`, script: { id: 's', name: 'CoDRIFT' }, dataset: { id: 'd', name: 'data.csv' },
  created_at: '2026-11-25T00:00:00Z', cancel_requested: false, total_count: 2, status: 'Queued',
  counts: { Queued: 2 }, axes: [], ...extra,
})

test('repository lists, loads and maps API sweeps into page shape', async () => {
  const run = { id: 'r0', sweep_index: 0, param_values: { k: '1' }, status: 'Queued', has_result: false, result_url: '' }
  const { request } = fakeServer({
    'GET /experiments/sweeps/': () => ({ sweeps: [apiSweep('a')] }),
    'GET /experiments/sweeps/a/': () => apiSweep('a', { status: 'Running', runs: [run] }),
  })
  const repository = createApiSweepRepository({ request })
  await repository.refresh()
  assert.equal(repository.getSnapshot().loading, false)
  assert.equal(repository.getSnapshot().sweeps[0].algorithm.name, 'CoDRIFT')
  const detail = await repository.load('a')
  assert.deepEqual(detail.experiments, [run])
  // Loading a detail keeps the list's status in step.
  assert.equal(repository.getSnapshot().sweeps[0].status, 'Running')
  assert.equal(await repository.load('missing'), null)
})

test('create, cancel and delete send CSRF-protected requests and update the snapshot', async () => {
  const server = fakeServer({
    'POST /experiments/sweeps/': ({ body }) => apiSweep('new', { name: body.name, runs: [] }),
    'POST /experiments/sweeps/new/cancel/': () => ({ ...apiSweep('new', { status: 'Cancelled', cancel_requested: true, runs: [] }), cancelled: 2 }),
    'DELETE /experiments/sweeps/new/': () => null,
  })
  const repository = createApiSweepRepository({ request: server.request })
  repository.setCsrfToken('token')
  const input = { name: ' Trees ', algorithm: { id: 's' }, dataset: { id: 'd' }, definitions, configuration: draft().configuration, parameterSweep: true }
  assert.deepEqual(await repository.create(input), { id: 'new', notice: '' })
  assert.equal(server.calls[0].body.name, 'Trees')
  assert.equal(server.calls[0].body.script_id, 's')
  assert.equal(server.calls[0].csrfToken, 'token')
  assert.equal(await repository.cancel('new'), 2)
  assert.equal(repository.getSnapshot().details.new.status, 'Cancelled')
  await repository.remove('new')
  assert.equal(repository.getSnapshot().details.new, undefined)
  assert.equal(server.calls.at(-1).method, 'DELETE')
})

test('a partially dispatched sweep still opens, with the server message as a notice', async () => {
  const { request } = fakeServer({
    'POST /experiments/sweeps/': () => { throw Object.assign(new Error('2 of 6 runs were queued'), { status: 503, payload: { sweep_id: 'half' } }) },
  })
  const repository = createApiSweepRepository({ request })
  const input = { name: 'x', algorithm: { id: 's' }, dataset: { id: 'd' }, definitions, configuration: draft().configuration, parameterSweep: true }
  assert.deepEqual(await repository.create(input), { id: 'half', notice: '2 of 6 runs were queued' })
})

test('errors include per-parameter messages and conflicting run numbers', () => {
  const error = Object.assign(new Error('Check the highlighted parameters.'), {
    payload: { errors: { numTrees: 'must be at least 1.' }, duplicate_conflicts: [{ sweep_index: 0 }, { sweep_index: 4 }] },
  })
  assert.equal(describeError(error), 'Check the highlighted parameters. numTrees: must be at least 1. Conflicting runs: #1, #5.')
  assert.equal(fromApiSweep(apiSweep('z')).experiments, undefined)
})
