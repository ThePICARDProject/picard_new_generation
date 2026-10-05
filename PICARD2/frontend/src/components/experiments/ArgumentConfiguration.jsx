import { useEffect, useId, useRef, useState } from 'react'
import { argumentError, defaultArguments } from '../../lib/argumentDefinitions'

export default function ArgumentConfiguration({ algorithmName, definitions, args, onApply, onCancel }) {
  const dialogRef = useRef(null)
  const titleId = useId()
  // Keep one string per field. Joining and splitting on spaces would corrupt
  // text arguments such as a model name containing more than one word.
  const [values, setValues] = useState(() => [...args])
  const [error, setError] = useState('')

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
    const message = argumentError(definitions, values)
    setError(message)
    if (!message) onApply(values)
  }

  return (
    <dialog ref={dialogRef} className="argument-dialog panel-card" aria-labelledby={titleId} onCancel={onCancel}>
      <p className="lcars-eyebrow">Experiment configuration</p>
      <h2 id={titleId}>{algorithmName} arguments</h2>
      <p className="helper-text">Choose a value for each argument. Available defaults are filled in to get you started.</p>
      {error ? <p className="message-banner message-banner-error" role="alert">{error}</p> : null}
      <form className="lcars-form" onSubmit={apply}>
        <div className="form-grid two-columns">
          {definitions.map((parameter, index) => {
            const helpId = `${titleId}-${parameter.name}`
            function changeValue(event) {
              setValues(values.map((value, position) => position === index ? event.target.value : value))
              setError('')
            }
            return (
              <label className="field" key={parameter.name}>
                <span>{parameter.label || parameter.name}</span>
                {parameter.type === 'choice' ? (
                  <select value={values[index]} required aria-describedby={helpId} onChange={changeValue}>
                    <option value="" disabled>Choose a value</option>
                    {parameter.choices.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
                  </select>
                ) : (
                  <input
                    type={parameter.type === 'string' ? 'text' : 'number'}
                    required
                    min={parameter.min ?? parameter.exclusiveMin}
                    max={parameter.max ?? parameter.exclusiveMax}
                    step={parameter.type === 'integer' ? 1 : 'any'}
                    value={values[index]}
                    aria-describedby={helpId}
                    onChange={changeValue}
                  />
                )}
                <small className="helper-text" id={helpId}>
                  {parameter.type}
                  {parameter.default !== undefined ? <> · Default: {String(parameter.default)}</> : null}
                  {parameter.choices ? <> · Choices: {parameter.choices.join(', ')}</> : null}
                  {parameter.min !== undefined ? <> · Minimum: {parameter.min}</> : null}
                  {parameter.max !== undefined ? <> · Maximum: {parameter.max}</> : null}
                  {parameter.exclusiveMin !== undefined ? <> · Greater than {parameter.exclusiveMin}</> : null}
                  {parameter.exclusiveMax !== undefined ? <> · Less than {parameter.exclusiveMax}</> : null}
                  {parameter.description ? <><br />{parameter.description}</> : null}
                </small>
              </label>
            )
          })}
        </div>
        <div className="form-actions">
          <button type="button" className="action-button secondary" onClick={() => {
            setValues(defaultArguments(definitions))
            setError('')
          }}>Reset defaults</button>
          <button type="button" className="action-button secondary" onClick={onCancel}>Cancel</button>
          <button type="submit" className="action-button">Apply</button>
        </div>
      </form>
    </dialog>
  )
}
