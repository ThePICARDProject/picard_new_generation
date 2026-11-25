import { createContext, useContext } from 'react'

export const SweepContext = createContext(null)
export function useSweeps() {
  const context = useContext(SweepContext)
  if (!context) throw new Error('useSweeps must be used inside SweepProvider')
  return context
}
