# Hyperparameter Grid Search Benchmark Summary

- **Algorithm Manifest:** `PICARD2/backend/scripts/manifests/supervisedmlrf.json`
- **Total Configurations Tested:** 8
- **Successful Runs:** 8
- **Failed Runs:** 0
- **Top-Performing Run:** `run_006`
  - **Accuracy:** `0.895`
  - **Duration:** `0.28s`
  - **Best Parameters:** `{'numClasses': '2', 'numTrees': '15', 'impurity': 'gini', 'maxDepth': '6', 'maxBins': '32', 'percentLabeled': '70'}`

| Rank | Run ID | Status | Duration | numClasses | numTrees | impurity | maxDepth | maxBins | percentLabeled | accuracy | executiontime_s | f1 | f1_score | maxdepth | precision | recall | time_taken_s | trees |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | run_006 | Success | 0.28s | 2 | 15 | gini | 6 | 32 | 70 | 0.895 | 0.2 | 0.886 | 0.886 | 6.0 | 0.8843 | 0.8878 | 0.2 | 15.0 |
| 2 | run_008 | Success | 0.28s | 2 | 15 | entropy | 6 | 32 | 70 | 0.89 | 0.201 | 0.8811 | 0.8811 | 6.0 | 0.8793 | 0.8829 | 0.201 | 15.0 |
| 3 | run_005 | Success | 0.28s | 2 | 15 | gini | 3 | 32 | 70 | 0.88 | 0.2 | 0.8712 | 0.8712 | 3.0 | 0.8694 | 0.873 | 0.2 | 15.0 |
| 4 | run_002 | Success | 0.20s | 2 | 5 | gini | 6 | 32 | 70 | 0.875 | 0.1 | 0.8662 | 0.8662 | 6.0 | 0.8645 | 0.868 | 0.1 | 5.0 |
| 5 | run_007 | Success | 0.30s | 2 | 15 | entropy | 3 | 32 | 70 | 0.875 | 0.201 | 0.8662 | 0.8662 | 3.0 | 0.8645 | 0.868 | 0.201 | 15.0 |
| 6 | run_004 | Success | 0.19s | 2 | 5 | entropy | 6 | 32 | 70 | 0.87 | 0.101 | 0.8613 | 0.8613 | 6.0 | 0.8596 | 0.863 | 0.101 | 5.0 |
| 7 | run_001 | Success | 0.18s | 2 | 5 | gini | 3 | 32 | 70 | 0.86 | 0.101 | 0.8514 | 0.8514 | 3.0 | 0.8497 | 0.8531 | 0.101 | 5.0 |
| 8 | run_003 | Success | 0.18s | 2 | 5 | entropy | 3 | 32 | 70 | 0.855 | 0.1 | 0.8464 | 0.8464 | 3.0 | 0.8447 | 0.8482 | 0.1 | 5.0 |
