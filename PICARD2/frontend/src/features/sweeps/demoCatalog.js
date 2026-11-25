import codrift from './fixtures/codrift.json'
import supervisedmlrf from './fixtures/supervisedmlrf.json'

// Snapshots of backend/scripts/manifests. No runtime dependency on Django.
export const demoAlgorithms = [
  { id: 'demo-codrift', name: 'CoDRIFT', file_type: 'jar', algorithm_config: codrift },
  { id: 'demo-supervisedmlrf', name: 'SupervisedMLRF', file_type: 'jar', algorithm_config: supervisedmlrf },
]

export const demoDatasets = [
  { id: 'demo-binary', name: 'Sample binary classification', file_name: 'binary-classification.csv' },
  { id: 'demo-sensor', name: 'Sample sensor readings', file_name: 'sensor-readings.csv' },
]
