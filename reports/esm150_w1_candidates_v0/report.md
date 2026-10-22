# W1 ESM-2 150M candidate inference

## Scope

This artifact applies the pinned author PEFT adapter to every row of the 201-row W1 candidate table. The model receives the full protein sequence, emits two logits at the target residue, and predicts by `argmax(logits)`.

The copied `label` column is retained for traceability only. It is not a model input, and this run contains no benchmark or inferred-vs-experimental performance metrics.

## Input

- Candidates: `D:\wbworkspace\glyco-analysis\reports\candidates_30_lora.csv`
- Candidate SHA256: `DBD51D28ABC0B0C74E78496E0A8F54CEBAA1C29F274B6E6B2716E39631A09FAB`
- Rows: `201`
- Accessions: `29`
- Unique sequences: `29`
- Label counts: `1=153`, `0=48`
- Ordered-key SHA256: `CCB02FF550D1CC1D9046F83A392E1E473CBE99ED4FD46D8F4FC2F4581BB2963A`

## Pinned model

- Adapter SHA256: `A4A5B486862724F459F60E8343AC135C340305D5A0F2E936EB5AD1DFD34788D4`
- Adapter tensors: `376`
- Base model: `facebook/esm2_t30_150M_UR50D`
- Base revision: `a695f6045e2e32885fa60af20c13cb35398ce30c`
- Base weights SHA256: `C3F1DA8AEA53BDDD32C246C86168C23B9FD72341FB9DB9A94436F855F5053566`

## Inference settings

- Precision: FP32
- Batch size: 1
- Sequence coverage: full sequence
- Truncation: none
- Windowing: none
- Attention backend: `sdpa`
- Decision rule: positive iff `logit_positive > logit_negative`
- Encoder forward count: 29, one per unique sequence

## Completion

`predictions.csv` and this report are hashed into `manifest.json`. The manifest is written last and marks the run complete.
