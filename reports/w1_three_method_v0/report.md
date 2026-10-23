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
| 1 | P04114:2982 | both_models_oppose_experimental_positive | ECO:0000269 | 0.335569 | 0.003845 | 0.992310 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 2 | Q6UWL2:470 | both_models_call_unannotated_control_positive | (none) | 0.650087 | 0.999982 | 0.999964 | NO_INDEPENDENT_EVIDENCE_FOUND |
| 3 | Q8TAV3:177 | esm35_opposes_experimental_positive | ECO:0000269 | 0.000016 | 0.999132 | 0.999969 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 4 | P04114:3358 | esm150_opposes_experimental_positive | ECO:0000269 | 0.644448 | 0.008536 | 0.982928 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 5 | Q6UWL2:503 | esm150_calls_unannotated_control_positive | (none) | 0.255392 | 0.999985 | 0.999969 | MISSED_ANNOTATION_CANDIDATE |
| 6 | P04114:3465 | both_models_oppose_experimental_positive | ECO:0000269 | 0.094834 | 0.005656 | 0.988688 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 7 | Q6UWL2:542 | both_models_call_unannotated_control_positive | (none) | 0.986805 | 0.999980 | 0.999960 | MISSED_ANNOTATION_CANDIDATE |
| 8 | P19827:285 | esm35_opposes_experimental_positive | ECO:0000269 | 0.010512 | 0.999975 | 0.978976 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 9 | P04114:185 | esm150_opposes_experimental_positive | ECO:0000269 | 0.864210 | 0.352208 | 0.295585 | SUPPORTED_EXPERIMENTAL_POSITIVE |
| 10 | Q6UWL2:308 | esm150_calls_unannotated_control_positive | (none) | 0.416532 | 0.999983 | 0.999966 | MISSED_ANNOTATION_CANDIDATE |

Selected row IDs: `P04114:2982`, `Q6UWL2:470`, `Q8TAV3:177`, `P04114:3358`, `Q6UWL2:503`, `P04114:3465`, `Q6UWL2:542`, `P19827:285`, `P04114:185`, `Q6UWL2:308`.

The generator emits `PENDING_MANUAL_REVIEW` by default. The outcomes above were manually reviewed on
2026-10-23 against cached GlyGen protein detail records and the associated PubMed, DOI, GlyConnect,
PDB, UniCarbKB, GPTwiki, and PDC identifiers. The review table keeps the original row order and the
original numeric fields. Only `review_status` and `reviewer_note` changed.

### Manual review outcomes

Six experimental positives have independent support: `P04114:2982`, `Q8TAV3:177`,
`P04114:3358`, `P04114:3465`, `P19827:285`, and `P04114:185`. The evidence includes
PubMed 32125861, 20805301, 26787547, 14760718, 19159218, 16335952, 23090970,
9425062, 9677337, 29671580, 37074911, 29741879, GlyConnect 57 and 284, PDB
9BD1, 9BD8, 9BDE and 9BDT, UniCarbKB GLY_000040, GPTwiki, PDC000471, and
GlyGen GLY_000143 and GLY_000481.

Three unannotated controls are annotation-review candidates: `Q6UWL2:308`
(GlyGen reported; PubMed 24190977 and GLY_000143, plus PDC000471 via PubMed
37074911), `Q6UWL2:503`, and `Q6UWL2:542` (both from DOI
10.1101/2023.09.13.557529 and data submission GLY_000888). The 503 and 542
records are preprint and submission level evidence, so they are candidates for
curator review and are not confirmed missed annotations. The benchmark labels
and metrics in this run remain unchanged.

`Q6UWL2:470` has `NO_INDEPENDENT_EVIDENCE_FOUND`. No exact-site record or
independent literature or structure evidence was found for this model-positive
control. This is an absence of supporting evidence, not a confirmed negative.

No author-replay prediction input was read or used.
