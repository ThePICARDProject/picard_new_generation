// The uploaded manifest is the single source of parameter names and defaults.
// A missing manifest means the algorithm still uses the manual argument box.
export function getArgumentDefinitions(script) {
  return script?.algorithm_config?.parameters ?? null
}

export function defaultArguments(definitions) {
  return definitions.map((parameter) => {
    if (parameter.default === undefined) return ''
    const value = String(parameter.default)
    return parameter.type === 'choice'
      ? parameter.choices.find((choice) => choice.toLowerCase() === value.toLowerCase())
      : value
  })
}

export function argumentError(definitions, values) {
  // Give immediate feedback in the form. The backend repeats these checks
  // because clients can also create experiments without using this screen.
  for (const [index, parameter] of definitions.entries()) {
    const value = values[index] ?? ''
    const label = parameter.label || parameter.name
    if (!value.trim()) return `${label} is required.`
    if (parameter.type !== 'integer' && parameter.type !== 'number') continue
    const number = Number(value)
    if (!Number.isFinite(number) || (parameter.type === 'integer' && !/^[+-]?[0-9]+$/.test(value))) {
      return `${label} must be a finite ${parameter.type}.`
    }
    if (parameter.min !== undefined && number < parameter.min) return `${label} must be at least ${parameter.min}.`
    if (parameter.max !== undefined && number > parameter.max) return `${label} must be at most ${parameter.max}.`
    if (parameter.exclusiveMin !== undefined && number <= parameter.exclusiveMin) return `${label} must be greater than ${parameter.exclusiveMin}.`
    if (parameter.exclusiveMax !== undefined && number >= parameter.exclusiveMax) return `${label} must be less than ${parameter.exclusiveMax}.`
  }
  return ''
}
