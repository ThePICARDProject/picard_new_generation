import { useEffect, useEffectEvent } from 'react'

export const POLL_INTERVAL_MS = 4000

// Call `poll` every few seconds while `active` is true. Polling stops when
// the sweep finishes (active becomes false) and when the page unmounts.
export function usePolling(poll, active, interval = POLL_INTERVAL_MS) {
  const onTick = useEffectEvent(() => { poll() })
  useEffect(() => {
    if (!active) return undefined
    const id = window.setInterval(onTick, interval)
    return () => window.clearInterval(id)
  }, [active, interval])
}
