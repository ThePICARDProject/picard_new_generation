// Vite replaces DEV with false in production, even if the demo flag is set.
export const SWEEPS_DEMO_MODE = import.meta.env.DEV && import.meta.env.VITE_SWEEPS_DEMO_MODE === 'true'
