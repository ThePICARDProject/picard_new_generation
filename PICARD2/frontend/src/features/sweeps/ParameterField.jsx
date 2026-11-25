export default function ParameterField({ parameter, configuration, onChange, error, allowVariation = true }) {
  const label = parameter.label || parameter.name
  const numeric = ['integer', 'number'].includes(parameter.type)
  const id = `sweep-parameter-${parameter.name}`
  const describe = `${id}-help${error ? ` ${id}-error` : ''}`
  const inputProps = { 'aria-describedby': describe, 'aria-invalid': Boolean(error) }
  return <article className={`sweep-parameter ${configuration.vary ? 'is-varied' : ''} ${error ? 'has-error' : ''}`}>
    <div className="sweep-parameter-heading"><div><h3>{label}</h3><code>{parameter.name}</code> <span className="sweep-type">{parameter.type}</span></div>
      {allowVariation ? <label className="sweep-toggle"><input type="checkbox" checked={configuration.vary} onChange={(event) => onChange({ vary: event.target.checked })} /><span>Vary {parameter.name}</span></label> : null}</div>
    <p className="helper-text" id={`${id}-help`}>
      {parameter.default !== undefined ? `Default: ${parameter.default}. ` : ''}
      {parameter.min !== undefined ? `Min: ${parameter.min}. ` : ''}{parameter.max !== undefined ? `Max: ${parameter.max}. ` : ''}
      {parameter.exclusiveMin !== undefined ? `Greater than ${parameter.exclusiveMin}. ` : ''}{parameter.exclusiveMax !== undefined ? `Less than ${parameter.exclusiveMax}. ` : ''}
      {parameter.description}
    </p>
    {!configuration.vary ? <label className="field"><span>Fixed value for {parameter.name}</span>
      {parameter.type === 'choice' ? <select {...inputProps} value={configuration.value} onChange={(event) => onChange({ value: event.target.value })}><option value="" disabled>Choose a value</option>{parameter.choices.map((choice) => <option key={choice}>{choice}</option>)}</select>
        : <input {...inputProps} type={numeric ? 'number' : 'text'} step={parameter.type === 'integer' ? 1 : 'any'} value={configuration.value} onChange={(event) => onChange({ value: event.target.value })} />}</label>
      : <>
        {numeric ? <label className="field sweep-mode-select"><span>Input method for {parameter.name}</span><select value={configuration.mode} onChange={(event) => onChange({ mode: event.target.value })}><option value="values">Explicit values</option><option value="range">Start / end / step</option></select></label> : null}
        {parameter.type === 'choice' ? <fieldset className="sweep-choice-group"><legend>Candidate values for {parameter.name}</legend>{parameter.choices.map((choice) => <label key={choice}><input {...inputProps} type="checkbox" checked={configuration.selected.includes(choice)} onChange={(event) => onChange({ selected: event.target.checked ? [...configuration.selected, choice] : configuration.selected.filter((value) => value !== choice) })} />{choice}</label>)}</fieldset>
          : numeric && configuration.mode === 'range' ? <div className="sweep-range-fields">{['start', 'end', 'step'].map((key) => <label className="field" key={key}><span>{key} for {parameter.name}</span><input {...inputProps} type="number" step={parameter.type === 'integer' ? 1 : 'any'} value={configuration[key]} onChange={(event) => onChange({ [key]: event.target.value })} /></label>)}<p className="helper-text">Ascending range; the end is included when reached by the step.</p></div>
            : <label className="field"><span>Candidate values for {parameter.name}</span><textarea {...inputProps} rows={2} value={configuration.candidates} placeholder={numeric ? '10, 20, 30' : 'One candidate per line'} onChange={(event) => onChange({ candidates: event.target.value })} /><small className="helper-text">Separate values with commas or new lines. Duplicate values count once.{parameter.type === 'string' ? ' Spaces within a value are preserved.' : ''}</small></label>}
      </>}
    {error ? <p className="sweep-field-error" id={`${id}-error`} role="alert">{error}</p> : null}
  </article>
}
