import { advanceSweeps, buildSweepPlan, cancelSweep, RUN_STATUSES } from './sweepModel.js'

export const SWEEP_STORAGE_KEY = 'picard.sweeps.demo.v1'

// UI depends only on this repository contract. A future API adapter can expose
// the same snapshot/subscription and create/cancel/refresh methods.
export function createDemoSweepRepository({ storage, now = Date.now, makeId = () => crypto.randomUUID(), withLock = (action) => action() }) {
  let snapshot = { sweeps: [], error: '', loading: true }
  const listeners = new Set()
  function publish(sweeps, error = '') {
    snapshot = { sweeps, error, loading: false }
    listeners.forEach((listener) => listener())
  }
  function read() {
    const raw = storage.getItem(SWEEP_STORAGE_KEY)
    if (!raw) return []
    let value
    try { value = JSON.parse(raw) } catch {
      throw new Error('Saved demo data could not be read. Clear the picard.sweeps.demo.v1 storage entry to start again.')
    }
    if (value.version !== 1 || !Array.isArray(value.sweeps) || !value.sweeps.every((sweep) =>
      typeof sweep.id === 'string' && typeof sweep.name === 'string' && sweep.algorithm?.name && sweep.dataset?.name &&
      Array.isArray(sweep.axes) && Array.isArray(sweep.experiments) && sweep.experiments.length > 0 &&
      sweep.experiments.every((run) => RUN_STATUSES.includes(run.status) && run.param_values && typeof run.id === 'string'))) {
      throw new Error('Saved demo data is not compatible. Clear the picard.sweeps.demo.v1 storage entry to start again.')
    }
    return value.sweeps
  }
  function fail(error) {
    publish(snapshot.sweeps, `Demo storage: ${error.message || 'Local storage is unavailable. Enable browser storage and retry.'}`)
  }
  async function mutate(change) {
    try {
      return await withLock(() => {
        const previous = read()
        const { sweeps, result } = change(previous)
        if (sweeps !== previous) storage.setItem(SWEEP_STORAGE_KEY, JSON.stringify({ version: 1, sweeps }))
        // Do not acknowledge a creation or cancellation until persistence succeeds.
        if (JSON.stringify(sweeps) !== JSON.stringify(snapshot.sweeps) || snapshot.error) publish(sweeps)
        return result
      })
    } catch (error) {
      fail(error)
      throw error
    }
  }
  return {
    available: true,
    getSnapshot: () => snapshot,
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener) },
    refresh: async () => { try { publish(read()) } catch (error) { fail(error) } },
    create: async ({ name, algorithm, dataset, configuration, parameterSweep = true }) => {
      if (!name.trim() || name.trim().length > 120) throw new Error('Enter an experiment name of 1–120 characters.')
      if (!algorithm?.algorithm_config?.parameters?.length || !dataset?.id) throw new Error('Select an algorithm with a manifest and a dataset.')
      const plan = buildSweepPlan(algorithm.algorithm_config.parameters, configuration, { varyParameters: parameterSweep })
      if (plan.error) throw new Error(plan.error)
      return mutate((previous) => {
        const id = makeId(), createdAt = now()
        const sweep = {
          id, name: name.trim(), algorithm: { id: algorithm.id, name: algorithm.name }, dataset: { id: dataset.id, name: dataset.name },
          created_at: createdAt, cancel_requested: false, total_count: plan.count, axes: plan.axes,
          parameters: configuration, parameter_sweep: parameterSweep,
          experiments: plan.combinations.map((values, index) => ({
            id: `${id}-${index + 1}`, batch: id, sweep_index: index + 1, param_values: values,
            args: algorithm.algorithm_config.parameters.map((parameter) => String(values[parameter.name])),
            status: 'Queued', created_at: createdAt, output: 'Waiting for the simulated worker.', metrics: null,
          })),
        }
        return { sweeps: [sweep, ...previous], result: sweep }
      })
    },
    cancel: (id) => mutate((previous) => {
      if (!previous.some((sweep) => sweep.id === id)) throw new Error('This experiment no longer exists.')
      return { sweeps: previous.map((sweep) => sweep.id === id ? cancelSweep(sweep) : sweep) }
    }),
    tick: () => mutate((previous) => ({ sweeps: advanceSweeps(previous, now()) })),
  }
}

const unavailableSnapshot = { sweeps: [], error: '', loading: false }
export const unconnectedSweepRepository = {
  available: false,
  getSnapshot: () => unavailableSnapshot,
  subscribe: () => () => {},
  refresh: async () => {},
  create: async () => { throw new Error('Experiment execution is not connected yet.') },
  cancel: async () => { throw new Error('Experiment execution is not connected yet.') },
}
