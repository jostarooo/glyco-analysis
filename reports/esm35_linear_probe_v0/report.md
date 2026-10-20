# ESM-2 35M frozen linear probe

This report applies only to the F1 v0 candidate table. Label 0 means "not annotated with a verified UniProt N-linked site" and does not mean "verified negative".

External context only: the paper's 0.781 is from a different dataset and protocol. It is not this run's result and is not used in the generated metrics block.

## Run contract

- Model: `facebook/esm2_t12_35M_UR50D` at `6fbf070e65b0b7291e7bbcd451118c216cff79d8`
- Candidate SHA256: `A584C3814226B7287807676F65D5CFFE2F5D47A53BC00476A4B9945CB0719F1C`
- UniProt release: `2026_03`
- Split: `leave_one_protein_out`
- Representation: `last_hidden_state_at_target_token`
- Rows / proteins / unique windows: 201 / 29 / 82
- Classifier: `LogisticRegression` with C=1.0, class_weight=none, solver=liblinear
- Threshold: 0.5
- Base commit at generation: `f5c8758017c6f71706bad3b5b26e4cba2f1eb8c1` (dirty=true)
- Device and dtype: `cuda` / `float32`

## Reproduce

```powershell
.venv\Scripts\python.exe scripts\run_esm35_linear_probe.py --cache-dir <uniprot-cache> --out-dir reports\esm35_linear_probe_v0
.venv\Scripts\python.exe scripts\check_esm35_linear_probe.py --run-dir reports\esm35_linear_probe_v0 --cache-dir <uniprot-cache>
```

## Environment

- Python 3.12.14
- torch 2.9.1+cu128
- transformers 5.20.1
- scikit-learn 1.9.1
- NumPy 2.5.4

## Result

<!-- BEGIN GENERATED METRICS -->
| metric | value |
|---|---:|
| MCC | 0.356452 |
| sensitivity | 0.797386 |
| specificity | 0.583333 |
| precision | 0.859155 |
| accuracy | 0.746269 |
| ROC AUC | 0.789624 |
| confusion | TN=28 FP=20 FN=31 TP=122 |

2000 protein-bootstrap replicates over 29 proteins. This is a 29-protein resampling interval, not a generalisation guarantee.
Valid replicates: 2000; undefined: 0.

| interval | 95% |
|---|---:|
| MCC | [0.130687, 0.581947] |
| sensitivity | [0.671222, 0.901107] |
| specificity | [0.373108, 0.809524] |
<!-- END GENERATED METRICS -->
