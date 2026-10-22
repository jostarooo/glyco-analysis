# W1 three-method comparison

## Evaluation boundary

- Source candidates: 201 rows.
- Honest metrics population: 130 rows (82 experimental positives + 48 unannotated controls), spanning 28 proteins.
- Display-only inferred positives: 71 rows. They remain in `comparison.csv` with a blank evaluation label and are excluded from every metric denominator.
- The controls are unannotated sequons, not confirmed biological negatives.
- UniProt N-linked annotation is the benchmark label source and reference ceiling, not a method.

## Methods

| method | decision rule | MCC | positive recall | control specificity | positive precision | weak-label accuracy | ROC AUC |
|---|---|---:|---:|---:|---:|---:|---:|
| sequon_rule | always positive; every row is an N-X-S/T sequon | 0.000000 | 1.000000 | 0.000000 | 0.630769 | 0.630769 | NA |
| esm35_oof | stored probability >= 0.5 | 0.331975 | 0.731707 | 0.604167 | 0.759494 | 0.684615 | 0.756098 |
| esm150_author_adapter | logit_positive > logit_negative | -0.232614 | 0.865854 | 0.000000 | 0.596639 | 0.546154 | 0.618140 |

The 35M scores are windowed leave-one-protein-out OOF estimates; the 150M scores are full-sequence author-adapter inference. A difference therefore combines model size, training procedure, adapter, and input-context differences and cannot be attributed to model size alone.

## Disagreement strata

- `both_models_oppose_experimental_positive`: 9 honest rows
- `both_models_call_unannotated_control_positive`: 19 honest rows
- `esm35_opposes_experimental_positive`: 13 honest rows
- `esm150_opposes_experimental_positive`: 2 honest rows
- `esm35_calls_unannotated_control_positive`: 0 honest rows
- `esm150_calls_unannotated_control_positive`: 29 honest rows
- `all_agree`: 58 honest rows

## Review sample

Selection policy: `w1-disagreement-v1`, honest 130-row pool only, round-robin across the six priority strata, then descending confidence margin within each stratum and accession,pos ties.

| rank | row_id | stratum | evidence | ESM-35M | ESM-150M | margin | status |
|---:|---|---|---|---:|---:|---:|---|
| 1 | P04114:2982 | both_models_oppose_experimental_positive | ECO:0000269 | 0.335569 | 0.003845 | 0.992310 | PENDING_MANUAL_REVIEW |
| 2 | Q6UWL2:470 | both_models_call_unannotated_control_positive | (none) | 0.650087 | 0.999982 | 0.999964 | PENDING_MANUAL_REVIEW |
| 3 | Q8TAV3:177 | esm35_opposes_experimental_positive | ECO:0000269 | 0.000016 | 0.999132 | 0.999969 | PENDING_MANUAL_REVIEW |
| 4 | P04114:3358 | esm150_opposes_experimental_positive | ECO:0000269 | 0.644448 | 0.008536 | 0.982928 | PENDING_MANUAL_REVIEW |
| 5 | Q6UWL2:503 | esm150_calls_unannotated_control_positive | (none) | 0.255392 | 0.999985 | 0.999969 | PENDING_MANUAL_REVIEW |
| 6 | P04114:3465 | both_models_oppose_experimental_positive | ECO:0000269 | 0.094834 | 0.005656 | 0.988688 | PENDING_MANUAL_REVIEW |
| 7 | Q6UWL2:542 | both_models_call_unannotated_control_positive | (none) | 0.986805 | 0.999980 | 0.999960 | PENDING_MANUAL_REVIEW |
| 8 | P19827:285 | esm35_opposes_experimental_positive | ECO:0000269 | 0.010512 | 0.999975 | 0.978976 | PENDING_MANUAL_REVIEW |
| 9 | P04114:185 | esm150_opposes_experimental_positive | ECO:0000269 | 0.864210 | 0.352208 | 0.295585 | PENDING_MANUAL_REVIEW |
| 10 | Q6UWL2:308 | esm150_calls_unannotated_control_positive | (none) | 0.416532 | 0.999983 | 0.999966 | PENDING_MANUAL_REVIEW |

Selected row IDs: `P04114:2982`, `Q6UWL2:470`, `Q8TAV3:177`, `P04114:3358`, `Q6UWL2:503`, `P04114:3465`, `Q6UWL2:542`, `P19827:285`, `P04114:185`, `Q6UWL2:308`.

No author-replay prediction input was read or used.
