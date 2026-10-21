# ESM-2 150M LoRA author-checkpoint reproduction

## Scope

The run evaluates every row of the author's `test.csv` in original order. No non-canonical or non-sequon rows are removed. The model uses the full protein sequence, the author's PEFT adapter, two logits, and `argmax`.

## Result

- MCC: `0.848348842859`
- Reference MCC: `0.848`
- Difference from reference: `+0.000348842859`
- Accuracy: `0.923649177760`
- Precision: `0.945967741935`
- Recall: `0.901614142967`
- Specificity: `0.946528332003`
- TP / FP / TN / FN: `1173` / `67` / `1186` / `128`

## Data audit

- Rows: `2554`
- Positives / negatives: `1301` / `1253`
- Non-sequon rows retained: `46`
- Unique sequences / encoder passes: `963`
- Longest sequence: `5179` residues
- Attention path: `sdpa` with full-sequence inference

## Compatibility note

The author adapter was saved with an older PEFT layout. The reproduction uses the author-pinned stack `peft 0.14.0` and `transformers 4.50.3` through an isolated overlay.

The `sdpa` path keeps the full sequence and uses PyTorch's memory-efficient scaled dot-product attention. It is an execution optimization, not a truncation or windowing change; the manifest records the selected backend.

Captured load warnings:

- `Found missing adapter keys while loading the checkpoint: ['base_model.model.classifier.original_module.out_proj.lora_A.default.weight', 'base_model.model.classifier.original_module.out_proj.lora_B.default.weight']`

The difference is reported as measured. Any attribution must be supported by the manifest, row predictions, and checker result.
