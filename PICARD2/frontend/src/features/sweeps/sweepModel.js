import { argumentError, defaultArguments } from '../../lib/argumentDefinitions.js'

export const MAX_EXPERIMENTS = 250
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
  const counts = Object.fromEntries(RUN_STATUSES.map((status) => [status, 0]))
  for (const experiment of sweep.experiments) counts[experiment.status]++
  const total = sweep.experiments.length
  const completed = counts.Success + counts.Failed
  const settled = completed + counts.Cancelled
  return { ...counts, total, completed, settled, progress: total ? Math.round(settled / total * 100) : 0 }
}

// Precedence matches the Data Model and Run Lifecycle specification exactly.
export function sweepStatus(sweep) {
  const counts = sweepCounts(sweep)
  if (counts.Running) return 'Running'
  if (counts.Queued || counts.Pending) return 'Queued'
  if (sweep.cancel_requested && counts.Cancelled) return 'Cancelled'
  if (counts.total && counts.Success === counts.total) return 'Success'
  return 'Completed with failures'
}

export function cancelSweep(sweep) {
  return { ...sweep, cancel_requested: true, experiments: sweep.experiments.map((run) => run.status === 'Queued'
    ? { ...run, status: 'Cancelled', output: 'Cancelled before execution. This run will not start.' } : run) }
}

// One simulated worker across ALL sweeps, with no background catch-up on refresh.
export function advanceSweeps(sweeps, now) {
  const runningSweep = sweeps.find((sweep) => sweep.experiments.some((run) => run.status === 'Running'))
  if (runningSweep) {
    const run = runningSweep.experiments.find((item) => item.status === 'Running')
    if (now - run.started_at < run.duration_ms) return sweeps
    const failed = run.sweep_index % 5 === 4
    return sweeps.map((sweep) => sweep.id !== runningSweep.id ? sweep : { ...sweep, experiments: sweep.experiments.map((item) => item.id !== run.id ? item : {
      ...item, status: failed ? 'Failed' : 'Success', finished_at: now,
      metrics: failed ? null : { accuracy: Number((0.81 + (run.sweep_index * 17 % 160) / 1000).toFixed(3)), duration_seconds: run.duration_ms / 1000 },
      output: failed ? 'Simulated Spark failure: executor could not complete this configuration. Other experiments will continue.' : 'Simulated Spark job completed. Mock evaluation metrics are ready.',
    }) })
  }
  const nextSweep = [...sweeps].reverse().find((sweep) => !sweep.cancel_requested && sweep.experiments.some((run) => run.status === 'Queued'))
  if (!nextSweep) return sweeps
  const next = nextSweep.experiments.find((run) => run.status === 'Queued')
  return sweeps.map((sweep) => sweep.id !== nextSweep.id ? sweep : { ...sweep, experiments: sweep.experiments.map((run) => run.id !== next.id ? run : {
    ...run, status: 'Running', started_at: now, duration_ms: 6000 + run.sweep_index % 3 * 1000,
    output: 'Simulated worker acquired experiment. Preparing dataset and fitting the Spark model…',
  }) })
}
