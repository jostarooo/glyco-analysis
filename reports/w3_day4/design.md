# Three-model Doc2Agent report

## Usage sketch

The caller supplies one manifest. The manifest names exactly three models, their run directories, their grade directories, the reference model, and an optional historical provenance sidecar.

```powershell
$env:PYTHONUTF8='1'
D:\python\python.exe scripts\doc2agent_three_model_report.py `
  --manifest reports\w3_day4\f3_models.json `
  --json-out reports\w3_day4\f3_three_model_report.json `
  --md-out reports\w3_day4\f3_three_model_report.md
```

The check mode regenerates both reports in memory and fails when either output is missing or differs.

```powershell
D:\python\python.exe scripts\doc2agent_three_model_report.py `
  --manifest reports\w3_day4\f3_models.json `
  --json-out reports\w3_day4\f3_three_model_report.json `
  --md-out reports\w3_day4\f3_three_model_report.md `
  --check
```

The public Python interface is one function:

```python
from scripts.doc2agent_three_model_report import build_report

report = build_report(Path("reports/w3_day4/f3_models.json"))
```

## Problem

The repository already has two-model run comparisons and two-model answer-grade comparisons. Adding a third model by calling both scripts and merging their outputs would create two report formats, two metric definitions, and a hand-written join.

The three-model report has to keep trajectory metrics separate from answer-grade metrics. It also has to prove that all three models used the same task set, the same prompt contract, and the same grading contract. The older Qwen run predates runtime prompt hash recording, so the report needs an explicit historical provenance path instead of assuming equality.

## Shape

`ModelSnapshot` is the domain boundary. It holds one model's run summary, grade summary, 50 run tasks, 50 grade tasks, prompt provenance, source hashes, trajectory metrics, diagnostics, and answer-grade metrics. Manifest entries only identify locations and labels. Model names are never branches in logic.

`build_report` owns the complete report operation. It loads each snapshot, checks snapshots against each other, derives report rows, and returns one JSON-compatible object. The Markdown renderer reads that object and does not maintain a second data source.

Validation lives at the artifact boundary. The loader rejects missing files, extra or missing task files, mismatched questions or expected tools, inconsistent run settings, mismatched prompt hashes, mixed grading contracts, edited grade summaries, and run-summary hash drift. Internal report construction trusts the validated snapshots.

The output keeps `trajectory` and `answer_grade` in separate objects. Every delta is named as `model_minus_reference_model`, and the reference key is repeated beside the delta. There is no combined accuracy field.

The public interface hides task discovery, source aggregation, cross-model validation, prompt provenance, metric recomputation, delta calculation, and deterministic serialization behind one function. The caller does not coordinate stages.

## Candidate A: manifest-driven snapshots

One loader creates three `ModelSnapshot` values. One builder validates the snapshots as a set and returns the report. JSON and Markdown are renderings of that report.

This candidate gives one model collection, one contract, one validation path, and one three-model entry. It handles the difference between old Qwen artifacts and current artifacts inside prompt provenance resolution.

## Candidate B: extend and merge the two-model scripts

Add a third directory argument to the existing run comparison and answer-grade comparison, then write a merge script for the two intermediate reports.

This candidate is rejected. It preserves two report schemas, repeats model and metric lists, and makes the merge layer a pass-through. It also encourages the three-model layer to import private helpers from two CLI modules.

## Red-flag table

| Check | Candidate A | Candidate B |
|---|---|---|
| Shallow module | Pass. One builder hides loading, validation, aggregation, and rendering. | Fail. A merge layer mostly forwards fields from two old reports. |
| Information leakage | Pass. Raw run and grade artifacts become `ModelSnapshot` values. | Fail. Two-model report schemas leak into the three-model layer. |
| Temporal decomposition | Pass. Ownership follows model artifacts, not load and render phases. | Fail. Old run comparison, old grade comparison, and a merge stage split one report. |
| Pass-through method | Pass. `build_report` performs the report operation. | Fail. The merge function mostly copies fields. |
| Split ownership | Pass. The manifest owns model membership and the builder owns output. | Fail. Model and metric lists exist in old scripts and the merge script. |
| Two ways to do one task | Pass for the new three-model scope. Existing two-model reports remain historical regeneration paths. | Fail. Two-model merge and three-model report become competing paths. |
| Importable internals | Pass. Only `build_report` is public. | Fail. The new path would import old CLI internals. |
| Hand-synced list | Pass. One manifest and one metric registry drive the report. | Fail. Model order, metric columns, and source paths appear in several places. |

## Synthesis decision

Candidate A is the base. The synthesized design keeps the single manifest, one `ModelSnapshot` collection, one validation pass, and one report object. It adds explicit historical provenance for the old Qwen run because runtime prompt hashes were not recorded there. It does not migrate or delete the existing two-model report scripts. Those scripts remain historical regeneration paths for their earlier two-model reports. This script is the only three-model report entry.

## Tradeoffs accepted

We accept a stricter report input contract in exchange for making cross-model claims auditable. Missing prompt provenance or missing grade fields stop the report instead of producing partial confidence.

We accept a larger validation module in exchange for one three-model entry point. The alternative distributes the same rules across two legacy comparators and a merge script.

We accept that the Qwen prompt contract is historical evidence, not runtime evidence. The report names that distinction in every source record.

## Implementation reconciliation

The implementation follows the synthesized shape. The only added detail is the aggregate source hash for each set of 50 JSON task files. It hashes a canonical list of filename and file SHA256 pairs so the report records both the directory identity and each task file.

## Next implementation step

Run the focused unit tests against temporary 3 by 50 fixtures, then run the report against the real manifest once the DeepSeek 50-task run and Kimi K3 grades are present.
