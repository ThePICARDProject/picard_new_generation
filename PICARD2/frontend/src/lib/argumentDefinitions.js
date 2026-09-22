// Stage one: local metadata. Keep the ordered definitions separate from the form
// so a future script API can supply them without changing the configuration UI.
// Order/types follow the legacy edu.fsu.driver.CoDRIFt main method; defaults
// are the demo preset. These are input bounds, not dataset compatibility checks.
const INT_MAX = 2147483647
export const codriftParameters = [
  { name: 'numClasses', label: 'Number of classes', type: 'integer', defaultValue: 2, min: 2, max: INT_MAX },
  { name: 'numTrees', label: 'Number of trees', type: 'integer', defaultValue: 10, min: 1, max: INT_MAX },
  { name: 'impurity', label: 'Impurity measure', type: 'choice', defaultValue: 'gini', choices: ['gini', 'entropy'] },
  { name: 'maxDepth', label: 'Maximum tree depth', type: 'integer', defaultValue: 5, min: 0, max: 30 },
  { name: 'maxBins', label: 'Maximum bins', type: 'integer', defaultValue: 32, min: 2, max: INT_MAX },
  { name: 'percentLabeled', label: 'Labelled data (%)', type: 'number', defaultValue: 70, min: 0, max: 100 },
  { name: 'k', label: 'Partition factor (k)', type: 'integer', defaultValue: 1, min: 1, max: 1073741823,
    description: 'CoDRIFT doubles this value to set the partition count.' },
]

export function getArgumentDefinitions(script) {
  if (!script) return null
  const mainClass = script.main_class?.trim().split('.').pop()
  return /^codrift$/i.test(mainClass || '') || /\bcodrift\b/i.test(script.name || '')
    ? codriftParameters
    : null
}

export function defaultArguments(definitions) {
  return definitions.map((parameter) => parameter.defaultValue).join(' ')
}
