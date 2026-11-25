import { argumentError, defaultArguments } from '../../lib/argumentDefinitions.js'

// Matches the backend default (SWEEP_MAX_EXPERIMENTS). The server's limit is
// authoritative; this only gives early feedback in the form.
export const MAX_EXPERIMENTS = 100
export const RUN_STATUSES = ['Pending', 'Queued', 'Running', 'Success', 'Failed', 'Cancelled']

export function initialConfiguration(definitions) {
  const defaults = defaultArguments(definitions)
  return Object.fromEntries(definitions.map((parameter, index) => [parameter.name, {
    vary: false, value: defaults[index] ?? '', mode: 'values',
    candidates: defaults[index] ?? '', selected: defaults[index] ? [defaults[index]] : [],
    start: defaults[index] ?? '', end: '', step: '1',
  }]))
}

function validateValue(parameter, value) {
  const error = argumentError([parameter], [value])
  if (error) throw new Error(error)
  if (parameter.type === 'choice' && !parameter.choices.includes(value)) {
    throw new Error(`Choose a valid value for ${parameter.label || parameter.name}.`)
  }
  if (parameter.type === 'integer' && !Number.isSafeInteger(Number(value))) {
    throw new Error(`${parameter.name} must be a safe integer.`)
  }
  if (!['integer', 'number', 'choice', 'string'].includes(parameter.type)) {
    throw new Error(`Unsupported parameter type: ${parameter.type}.`)
  }
  return ['integer', 'number'].includes(parameter.type) ? Number(value) : value
}

export function candidateValues(parameter, configuration) {
  let values
  if (!configuration.vary) {
    values = [configuration.value]
  } else if (configuration.mode === 'range' && ['integer', 'number'].includes(parameter.type)) {
    const { start, end, step } = configuration
    if ([start, end, step].some((value) => !String(value).trim())) throw new Error('Enter a start, end, and step.')
    const first = Number(start), last = Number(end), increment = Number(step)
    if (![first, last, increment].every(Number.isFinite) || increment <= 0 || last < first) {
      throw new Error('Use finite numbers, an end ≥ start, and a positive step.')
    }
    if (parameter.type === 'integer' && ![first, last, increment].every(Number.isSafeInteger)) {
      throw new Error('Integer ranges require whole-number start, end, and step values.')
    }
    validateValue(parameter, String(first))
    validateValue(parameter, String(last))
    const count = Math.floor((last - first) / increment + 1e-9) + 1
    if (count > MAX_EXPERIMENTS) throw new Error(`A range can contain at most ${MAX_EXPERIMENTS} values.`)
    values = Array.from({ length: count }, (_, index) => String(Number((first + index * increment).toPrecision(15))))
    if (values.length > 1 && new Set(values).size !== values.length) throw new Error('This step is too small for the selected range.')
  } else if (parameter.type === 'choice') {
    values = configuration.selected
  } else {
    // Newlines support multi-word string arguments; commas are also accepted.
    values = configuration.candidates.split(/[,\n]/).map((value) => value.trim())
  }
  if (!values?.length || values.some((value) => !String(value).trim())) {
    throw new Error('Enter at least one non-empty candidate; remove empty separators.')
  }
  if (values.length > MAX_EXPERIMENTS) throw new Error(`Use at most ${MAX_EXPERIMENTS} candidate values.`)
  return [...new Set(values.map((value) => validateValue(parameter, String(value))))]
}

export function buildSweepPlan(definitions, configuration, { varyParameters = true } = {}) {
  const errors = {}, axes = []
  for (const parameter of definitions) {
    try {
      const settings = varyParameters ? configuration[parameter.name] : { ...configuration[parameter.name], vary: false }
      axes.push({ name: parameter.name, varied: Boolean(settings?.vary), values: candidateValues(parameter, settings) })
    } catch (error) {
      errors[parameter.name] = error.message
    }
  }
  const varied = axes.filter((axis) => axis.varied)
  const count = axes.reduce((total, axis) => total * axis.values.length, 1)
  const error = Object.keys(errors).length ? 'Check the highlighted parameters.'
    : varyParameters && !varied.length ? 'Select at least one parameter to vary.'
      : count > MAX_EXPERIMENTS ? `This configuration creates ${count.toLocaleString()} runs. Reduce it to ${MAX_EXPERIMENTS} or fewer.` : ''
  const combinations = error ? [] : axes.reduce((rows, axis) => rows.flatMap((row) => axis.values.map((value) => ({ ...row, [axis.name]: value }))), [{}])
  return { errors, error, axes, varied, count: Object.keys(errors).length ? 0 : count, combinations }
}

export function sweepCounts(sweep) {
  // Prefer the server's counts; fall back to counting a loaded run table.
  const counts = Object.fromEntries(RUN_STATUSES.map((status) => [status, sweep.counts?.[status] ?? 0]))
  if (!sweep.counts) for (const experiment of sweep.experiments ?? []) counts[experiment.status]++
  const total = RUN_STATUSES.reduce((sum, status) => sum + counts[status], 0)
  const completed = counts.Success + counts.Failed
  const settled = completed + counts.Cancelled
  return { ...counts, total, completed, settled, progress: total ? Math.round(settled / total * 100) : 0 }
}

// Same precedence as the backend's batch_status(). The server's value wins
// when present; this keeps the UI consistent for locally derived counts.
export function sweepStatus(sweep) {
  if (sweep.status) return sweep.status
  const counts = sweepCounts(sweep)
  if (counts.Running) return 'Running'
  if (counts.Queued || counts.Pending) return 'Queued'
  if (sweep.cancel_requested && counts.Cancelled) return 'Cancelled'
  if (counts.total && counts.Success === counts.total) return 'Success'
  return 'Completed with failures'
}
