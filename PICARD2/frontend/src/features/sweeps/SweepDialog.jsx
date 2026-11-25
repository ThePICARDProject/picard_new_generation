import { useEffect, useId, useRef } from 'react'

export default function SweepDialog({ title, onClose, children }) {
  const ref = useRef(null)
  const id = useId()
  useEffect(() => {
    const dialog = ref.current
    const previousFocus = document.activeElement
    dialog.showModal()
    return () => { dialog.close(); previousFocus?.focus() }
  }, [])
  return <dialog ref={ref} className="argument-dialog panel-card sweep-dialog" aria-labelledby={id} onCancel={onClose}>
    <div className="panel-heading-row"><h2 id={id}>{title}</h2><button type="button" className="action-button secondary tiny" aria-label="Close dialog" onClick={onClose}>Close</button></div>
    {children}
  </dialog>
}
