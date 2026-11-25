// Connects the sweep pages to the Django API under /experiments/sweeps/.
// The pages read a snapshot through useSyncExternalStore, so every change
// goes through publish() below.

export const ACTIVE_STATUSES = ['Pending', 'Queued', 'Running']
export const isActive = (status) => ACTIVE_STATUSES.includes(status)

// Translate the builder's form state into the API's sweep definition:
// a fixed value, an explicit list, or an inclusive {start, stop, step} range.
export function toDefinition(definitions, configuration, parameterSweep) {
  return Object.fromEntries(definitions.map((parameter) => {
    const settings = configuration[parameter.name] || {}
    if (!parameterSweep || !settings.vary) return [parameter.name, settings.value]
    if (settings.mode === 'range' && ['integer', 'number'].includes(parameter.type)) {
      return [parameter.name, { start: settings.start, stop: settings.end, step: settings.step }]
    }
    if (parameter.type === 'choice') return [parameter.name, settings.selected]
    return [parameter.name, settings.candidates.split(/[,\n]/).map((value) => value.trim()).filter(Boolean)]
  }))
}

// API field names -> the names the pages use.
export function fromApiSweep(sweep) {
  return {
    id: sweep.id,
    name: sweep.name,
    algorithm: sweep.script,
    dataset: sweep.dataset,
    created_at: sweep.created_at,
    cancel_requested: sweep.cancel_requested,
    total_count: sweep.total_count,
    status: sweep.status,
    counts: sweep.counts,
    axes: sweep.axes,
    experiments: sweep.runs,
  }
}

export function requestBody({ name, algorithm, dataset, definitions, configuration, parameterSweep }) {
  return {
    name: name.trim(),
    script_id: algorithm.id,
    dataset_id: dataset.id,
    parameters: toDefinition(definitions, configuration, parameterSweep),
  }
}

// Turn an API error into one readable sentence, including field details.
export function describeError(error) {
  const payload = error?.payload
  const parts = [error?.message || 'Request failed.']
  if (payload?.errors && typeof payload.errors === 'object') {
    parts.push(...Object.entries(payload.errors).map(([name, message]) => `${name}: ${message}`))
  }
  if (Array.isArray(payload?.duplicate_conflicts) && payload.duplicate_conflicts.length) {
    parts.push(`Conflicting runs: ${payload.duplicate_conflicts.map((item) => `#${item.sweep_index + 1}`).join(', ')}.`)
  }
  return parts.join(' ')
}

export function createApiSweepRepository({ request }) {
  let csrfToken = ''
  const getCsrfToken = () => csrfToken
  let snapshot = { sweeps: [], details: {}, error: '', loading: true }
  const listeners = new Set()
  function publish(patch) {
    snapshot = { ...snapshot, ...patch }
    listeners.forEach((listener) => listener())
  }
  function storeDetail(apiSweep) {
    const sweep = fromApiSweep(apiSweep)
    publish({
      details: { ...snapshot.details, [sweep.id]: sweep },
      // Keep the list in step, so its badge does not lag behind the detail page.
      sweeps: snapshot.sweeps.map((item) => item.id === sweep.id ? { ...item, ...sweep, experiments: undefined } : item),
    })
    return sweep
  }
  const post = (path, body) => request(path, { method: 'POST', body, csrfToken: getCsrfToken() })

  const repository = {
    getSnapshot: () => snapshot,
    setCsrfToken: (token) => { csrfToken = token || '' },
    subscribe: (listener) => { listeners.add(listener); return () => listeners.delete(listener) },
    reset: () => publish({ sweeps: [], details: {}, error: '', loading: true }),

    async refresh() {
      try {
        const data = await request('/experiments/sweeps/')
        publish({ sweeps: data.sweeps.map(fromApiSweep), error: '', loading: false })
      } catch (error) {
        publish({ error: `Unable to load sweeps: ${error.message}`, loading: false })
      }
    },

    async load(id) {
      try {
        return storeDetail(await request(`/experiments/sweeps/${id}/`))
      } catch (error) {
        if (error.status === 404) {
          const { [id]: _removed, ...details } = snapshot.details
          publish({ details })
          return null
        }
        throw error
      }
    },

    preview: (input) => post('/experiments/sweeps/preview/', requestBody(input)),

    async create(input) {
      try {
        const sweep = storeDetail(await post('/experiments/sweeps/', requestBody(input)))
        return { id: sweep.id, notice: '' }
      } catch (error) {
        // 503 after a partial dispatch: the sweep exists, so open it anyway.
        if (error.status === 503 && error.payload?.sweep_id) return { id: error.payload.sweep_id, notice: error.message }
        throw error
      }
    },

    async cancel(id) {
      const result = await post(`/experiments/sweeps/${id}/cancel/`)
      storeDetail(result)
      return result.cancelled
    },

    async remove(id) {
      await request(`/experiments/sweeps/${id}/`, { method: 'DELETE', csrfToken: getCsrfToken() })
      const { [id]: _removed, ...details } = snapshot.details
      publish({ details, sweeps: snapshot.sweeps.filter((sweep) => sweep.id !== id) })
    },

    // Runs are ordinary experiments, so the existing endpoints apply.
    runDetail: (runId) => request(`/experiments/${runId}/`),
    async rerun(sweepId, runId) {
      await post(`/experiments/${runId}/run/`)
      return repository.load(sweepId)
    },
  }
  return repository
}
