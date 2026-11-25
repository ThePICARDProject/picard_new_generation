import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { advanceSweeps, buildSweepPlan, candidateValues, cancelSweep, initialConfiguration, sweepCounts, sweepStatus } from '../features/sweeps/sweepModel.js'
import { createDemoSweepRepository, SWEEP_STORAGE_KEY } from '../features/sweeps/sweepRepository.js'

const manifest = JSON.parse(readFileSync(new URL('../features/sweeps/fixtures/codrift.json', import.meta.url), 'utf8'))
const definitions = manifest.parameters
function draft() {
  const configuration = initialConfiguration(definitions)
  configuration.numTrees = { ...configuration.numTrees, vary: true, candidates: '10, 20, 30' }
  configuration.maxDepth = { ...configuration.maxDepth, vary: true, candidates: '5, 10' }
  configuration.impurity = { ...configuration.impurity, vary: true, selected: ['gini', 'entropy'] }
  return { name: 'CoDRIFT Hyperparameter Test', algorithm: { id: 'codrift', name: 'CoDRIFT', algorithm_config: manifest }, dataset: { id: 'sample', name: 'Sample dataset' }, configuration }
}
function memoryStorage() {
  const items = new Map()
  return { getItem: (key) => items.get(key) ?? null, setItem: (key, value) => items.set(key, value) }
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

test('a standard experiment creates one fixed run without requiring parameter variation', async () => {
  const storage = memoryStorage()
  const repository = createDemoSweepRepository({ storage, makeId: () => 'single' })
  const created = await repository.create({ ...draft(), parameterSweep: false })
  assert.equal(created.parameter_sweep, false)
  assert.equal(created.experiments.length, 1)
  assert.equal(created.axes.every((axis) => !axis.varied), true)
  assert.deepEqual(created.experiments[0].args, ['2', '10', 'gini', '5', '32', '70', '1'])
  const reloaded = createDemoSweepRepository({ storage })
  await reloaded.refresh()
  assert.deepEqual(reloaded.getSnapshot().sweeps, [created])
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
  assert.match(plan.error, /250 or fewer/)
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

test('cancelling changes only queued runs and is idempotent', () => {
  const original = batch(['Running', 'Queued', 'Success', 'Failed', 'Cancelled'])
  const cancelled = cancelSweep(original)
  assert.deepEqual(cancelled.experiments.map((run) => run.status), ['Running', 'Cancelled', 'Success', 'Failed', 'Cancelled'])
  assert.deepEqual(cancelSweep(cancelled), cancelled)
  assert.equal(original.experiments[1].status, 'Queued')
})

test('repository creates queued runs, persists, reloads, and retains structured parameters', async () => {
  const storage = memoryStorage()
  const repository = createDemoSweepRepository({ storage, now: () => 100, makeId: () => 'saved' })
  const created = await repository.create(draft())
  assert.equal(created.total_count, 12)
  assert.equal(created.experiments.every((run) => run.status === 'Queued'), true)
  assert.equal(created.experiments[0].batch, created.id)
  assert.deepEqual(created.experiments[0].args, ['2', '10', 'gini', '5', '32', '70', '1'])
  const reloaded = createDemoSweepRepository({ storage })
  await reloaded.refresh()
  assert.deepEqual(reloaded.getSnapshot().sweeps, [created])
  await reloaded.cancel(created.id)
  await repository.refresh()
  assert.equal(sweepStatus(repository.getSnapshot().sweeps[0]), 'Cancelled')
})

test('single worker across sweeps, queued cancellation cannot later start, running finishes', async () => {
  let time = 1000, id = 0
  const repository = createDemoSweepRepository({ storage: memoryStorage(), now: () => time, makeId: () => String(++id) })
  const first = await repository.create(draft())
  const second = await repository.create(draft())
  await repository.tick()
  let sweeps = repository.getSnapshot().sweeps
  assert.equal(sweeps.flatMap((sweep) => sweep.experiments).filter((run) => run.status === 'Running').length, 1)
  assert.equal(sweeps.find((sweep) => sweep.id === first.id).experiments[0].status, 'Running')
  await repository.cancel(first.id)
  await repository.tick()
  assert.equal(sweepStatus(repository.getSnapshot().sweeps.find((sweep) => sweep.id === first.id)), 'Running')
  time += 10000
  await repository.tick()
  sweeps = repository.getSnapshot().sweeps
  const cancelled = sweeps.find((sweep) => sweep.id === first.id)
  assert.equal(cancelled.experiments[0].status, 'Success')
  assert.equal(sweepCounts(cancelled).Cancelled, 11)
  assert.equal(sweepStatus(cancelled), 'Cancelled')
  await repository.tick()
  sweeps = repository.getSnapshot().sweeps
  assert.equal(sweeps.find((sweep) => sweep.id === second.id).experiments[0].status, 'Running')
  assert.equal(sweepCounts(sweeps.find((sweep) => sweep.id === first.id)).Cancelled, 11)
})

test('simulation reaches Success and Failed endings without concurrent runs', async () => {
  const repository = createDemoSweepRepository({ storage: memoryStorage(), makeId: () => 'finish' })
  const created = await repository.create(draft())
  let sweeps = [created]
  for (let tick = 1; tick <= 24; tick++) {
    sweeps = advanceSweeps(sweeps, tick * 10000)
    assert.ok(sweepCounts(sweeps[0]).Running <= 1)
  }
  assert.equal(sweepStatus(sweeps[0]), 'Completed with failures')
  assert.equal(sweepCounts(sweeps[0]).Success, 10)
  assert.equal(sweepCounts(sweeps[0]).Failed, 2)
  assert.equal(sweepCounts(sweeps[0]).progress, 100)
})

test('storage write failures are visible and creation is not acknowledged', async () => {
  const repository = createDemoSweepRepository({ storage: { getItem: () => null, setItem: () => { throw new Error('Quota exceeded') } } })
  await assert.rejects(repository.create(draft()), /Quota exceeded/)
  assert.equal(repository.getSnapshot().sweeps.length, 0)
  assert.match(repository.getSnapshot().error, /Quota exceeded/)
})

test('malformed storage is reported without overwriting the saved data', async () => {
  const storage = memoryStorage()
  storage.setItem(SWEEP_STORAGE_KEY, '{broken')
  const repository = createDemoSweepRepository({ storage })
  await repository.refresh()
  assert.ok(repository.getSnapshot().error)
  await assert.rejects(repository.create(draft()))
  assert.equal(storage.getItem(SWEEP_STORAGE_KEY), '{broken')
})
