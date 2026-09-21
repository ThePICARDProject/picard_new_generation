import { useEffect, useId, useRef, useState } from 'react'

export default function ArgumentConfiguration({ algorithmName, definitions, args, onApply, onCancel }) {
  const dialogRef = useRef(null)
  const titleId = useId()
  const [values, setValues] = useState(() => {
    const tokens = args.trim() ? args.trim().split(/\s+/) : []
    return Object.fromEntries(definitions.map((parameter, index) => [
      parameter.name, tokens[index] ?? String(parameter.defaultValue),
    ]))
  })

  useEffect(() => {
    const dialog = dialogRef.current
    const previousFocus = document.activeElement
    dialog.showModal()
    return () => {
      dialog.close()
      previousFocus?.focus()
    }
  }, [])

  function apply(event) {
    event.preventDefault()
    onApply(definitions.map((parameter) => (
      parameter.type === 'choice' ? values[parameter.name] : String(Number(values[parameter.name]))
    )).join(' '))
  }

  return (
    <dialog ref={dialogRef} className="argument-dialog panel-card" aria-labelledby={titleId} onCancel={onCancel}>
      <p className="lcars-eyebrow">Experiment configuration</p>
      <h2 id={titleId}>{algorithmName} arguments</h2>
      <p className="helper-text">Choose a value for each argument. Defaults are filled in to get you started.</p>
      <form className="lcars-form" onSubmit={apply}>
        <div className="form-grid two-columns">
          {definitions.map((parameter) => {
            const helpId = `${titleId}-${parameter.name}`
            return (
              <label className="field" key={parameter.name}>
                <span>{parameter.label}</span>
                {parameter.type === 'choice' ? (
                  <select
                    value={values[parameter.name]}
                    aria-describedby={helpId}
                    onChange={(event) => setValues({ ...values, [parameter.name]: event.target.value })}
                  >
                    {parameter.choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
                  </select>
                ) : (
                  <input
                    type="number"
                    ref={(input) => {
                      input?.setCustomValidity(
                        parameter.minExclusive && Number(values[parameter.name]) <= parameter.min
                          ? `Enter a value greater than ${parameter.min}.` : '',
                      )
                    }}
                    required
                    min={parameter.min}
                    max={parameter.max}
                    step={parameter.type === 'integer' ? 1 : 'any'}
                    value={values[parameter.name]}
                    aria-describedby={helpId}
                    onChange={(event) => setValues({ ...values, [parameter.name]: event.target.value })}
                  />
                )}
                <small className="helper-text" id={helpId}>
                  {parameter.type === 'integer' ? 'Integer' : parameter.type === 'choice' ? 'Choice' : 'Number'}
                  {' · Default: '}{parameter.defaultValue}
                  {' · Allowed: '}{parameter.choices ? parameter.choices.join(', ') : parameter.minExclusive ? `greater than ${parameter.min}, up to ${parameter.max}` : `${parameter.min}–${parameter.max}`}
                  {parameter.description ? <><br />{parameter.description}</> : null}
                </small>
              </label>
            )
          })}
        </div>
        <div className="form-actions">
          <button type="button" className="action-button secondary" onClick={() => setValues(
            Object.fromEntries(definitions.map((parameter) => [parameter.name, String(parameter.defaultValue)])),
          )}>Reset defaults</button>
          <button type="button" className="action-button secondary" onClick={onCancel}>Cancel</button>
          <button type="submit" className="action-button">Apply</button>
        </div>
      </form>
    </dialog>
  )
}
