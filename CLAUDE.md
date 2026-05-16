# chembl-antimicrobial-hub-incorporation

## Purpose

This repo handles the packaging and incorporation of the 15 pathogen-specific antimicrobial activity QSAR models (from `chembl-antimicrobial-models`) into the Ersilia Model Hub. **One Ersilia model per pathogen.**

The same workflow is repeated for every pathogen — this file describes the generic process. Per-pathogen progress is tracked in the [monitoring table](#monitoring-table) below.

This repo is a sibling of two others:
- `ersilia-os/chembl-antimicrobial-models` (training repo — source of all weights, reports, and consensus logic)
- `ersilia-os/chembl-antimicrobial-tasks` (task definitions used by LazyQSAR during training)

**PATH_TO_CAMM** is the local path to your clone of `chembl-antimicrobial-models`. Everything we need (model weights, quality reports, consensus scoring logic) is read from there. Set it before starting work in any session, e.g.:
```
PATH_TO_CAMM=/aloy/home/acomajuncosa/Ersilia/chembl-antimicrobial-models
```

---

## Monitoring table

Per-pathogen progress through the incorporation workflow. Update each column as the corresponding step completes.

| pathogen | issue # | forked to arnaucoma24 | model prepared | PR merged | workflows passed | fork removed |
|----------|---------|-----------------------|----------------|-----------|------------------|--------------|
| abaumannii    | [#1849](https://github.com/ersilia-os/ersilia/issues/1849) | True  | False | False | False | False |
| efaecium      | —    | False | False | False | False | False |
| saureus       | —    | False | False | False | False | False |
| kpneumoniae   | —    | False | False | False | False | False |
| paeruginosa   | —    | False | False | False | False | False |
| ecoli         | —    | False | False | False | False | False |
| mtuberculosis | —    | False | False | False | False | False |
| pfalciparum   | —    | False | False | False | False | False |
| calbicans     | —    | False | False | False | False | False |
| enterobacter  | —    | False | False | False | False | False |
| campylobacter | —    | False | False | False | False | False |
| hpylori       | —    | False | False | False | False | False |
| ngonorrhoeae  | —    | False | False | False | False | False |
| smansoni      | —    | False | False | False | False | False |
| spneumoniae   | —    | False | False | False | False | False |

Column meanings:
- **issue #** — ID of the model-request issue at `ersilia-os/ersilia` (an `eosXXXX` ID is assigned when the issue is approved).
- **forked to arnaucoma24** — auto-created `ersilia-os/eosXXXX` has been forked to `arnaucoma24/eosXXXX` and cloned locally.
- **model prepared** — checkpoints, `main.py`, `metadata.yml`, `install.yml`, columns and examples all in place and tested locally.
- **PR merged** — pull request from `arnaucoma24/eosXXXX` into `ersilia-os/eosXXXX` is merged.
- **workflows passed** — the GitHub Actions on the merged commit (model test workflows on `ersilia-os/eosXXXX`) are green.
- **fork removed** — `arnaucoma24/eosXXXX` fork has been deleted now that the model lives upstream.

---

## Overall workflow (per pathogen)

| Step | Action |
|------|--------|
| i    | Create GitHub issue at `ersilia-os/ersilia` requesting model incorporation |
| ii   | Once an `eosXXXX` ID is assigned and `ersilia-os/eosXXXX` is auto-created, fork it to `arnaucoma24` and clone locally |
| iii  | Prepare the model (checkpoints, code, metadata.yml) |
| iv   | Open pull request to `ersilia-os/eosXXXX` |
| v    | Once merged and workflows pass, delete the `arnaucoma24/eosXXXX` fork |

Update the [monitoring table](#monitoring-table) as each step completes.

---

## Step iii — Preparing the model (detailed)

The forked model repo (`arnaucoma24/eosXXXX`, to be PRed into `ersilia-os/eosXXXX`) has this structure:

```
eosXXXX/
├── metadata.yml          ← fill in all fields
├── install.yml           ← add all dependencies with pinned versions
├── model/
│   ├── checkpoints/      ← copy model weights here
│   └── framework/
│       ├── run.sh        ← already correct (calls main.py)
│       ├── code/
│       │   └── main.py   ← implement full inference pipeline
│       ├── columns/
│       │   └── run_columns.csv  ← define the output columns
│       └── examples/
│           ├── run_input.csv    ← 3 example SMILES
│           └── run_output.csv   ← expected output for those 3
```

### iii.1 — Checkpoints

Copy from `$PATH_TO_CAMM/output/results/09_models/{pathogen}/` into `model/checkpoints/`:

```
model/checkpoints/
├── individual_inhibition/     ← full sub-model dir (ONNX weights + featurizer.json + metadata.json)
├── merged_mic_decoys/
├── general_mic/
├── general_activity_decoys/
├── general_mic50/
├── featurizer_weights/        ← copy from $PATH_TO_CAMM/output/results/08_weights/.lazyqsar/
│   ├── chemeleon_mp.pt        (~200 MB — needed for Chemeleon featurizer)
│   ├── clamp_encoder.onnx     (~200 MB — needed for CLAMP featurizer)
│   ├── cddd_encoder.onnx      (needed for CDDD featurizer, if used)
│   └── cddd_encoder_smiles.csv
└── reports.csv                ← copy ONLY {pathogen} rows from $PATH_TO_CAMM/output/results/10_reports.csv
```

**Sub-models vary per pathogen.** The list above (5 sub-models) is the abaumannii case; for other pathogens, check which sub-model directories exist under `$PATH_TO_CAMM/output/results/09_models/{pathogen}/` and adapt the `model_dir_dict` in `main.py` and the output columns accordingly.

**Note on featurizer weights size**: `08_weights/.lazyqsar/` is ~612 MB total. These need to be in checkpoints so the Hub can serve them. Use Git LFS (`.gitattributes` is configured in the eosXXXX template for `*.pt`, `*.onnx`, `*.h5`).

Each sub-model directory looks like:
```
{model_name}/
├── metadata.json
├── featurizer.json
├── applicability_domain.onnx
├── applicability_domain.json
├── batch_0/
│   ├── preprocessor.onnx + preprocessor.json
│   ├── xgb.onnx + xgb.json         ← algorithm weights
│   └── rf.onnx + rf.json
└── batch_1/     ← only for models that have 2 batches (check num_batches in metadata.json)
```

### iii.2 — main.py

The inference pipeline must:

1. **Read SMILES** from the input CSV (one column, header = `smiles`)
2. **Run LazyQSAR inference** for all sub-models using the `lqsar_predict` API:

```python
from lazyqsar.api.classifier_predict import predict as lqsar_predict

# Point LazyQSAR to the featurizer weights
os.environ["HOME"] = os.path.join(root, "..", "checkpoints", "featurizer_weights_home")
# (create a dir that has .lazyqsar/ inside pointing to featurizer_weights/)

# Adapt this dict to the sub-models actually present for this pathogen
model_dir_dict = {
    "individual_inhibition":    os.path.join(checkpoints, "individual_inhibition"),
    "merged_mic_decoys":        os.path.join(checkpoints, "merged_mic_decoys"),
    "general_mic":              os.path.join(checkpoints, "general_mic"),
    "general_activity_decoys":  os.path.join(checkpoints, "general_activity_decoys"),
    "general_mic50":            os.path.join(checkpoints, "general_mic50"),
}

lqsar_predict(
    model_dir=model_dir_dict,
    input_csv=input_file,
    output_csv=tmp_output,
    predict_type="probability",   # NOT "rank" — ranks are relative to input set, meaningless for single compounds
)
```

3. **Compute the consensus score** as a quality-weighted average of the sub-model probabilities:

Quality weights come from `checkpoints/reports.csv` (w1–w7 columns).
Use the mean of w1–w7 as the scalar weight for each sub-model.
**Do not use w8** — w8 is rank-based (decision_cutoff_rank) and not meaningful for raw probabilities.

```python
import pandas as pd, numpy as np

reports = pd.read_csv(os.path.join(checkpoints, "reports.csv"))
W_COLS = ["w1","w2","w3","w4","w5","w6","w7"]
weights = {
    row["model_name"]: row[W_COLS].mean()
    for _, row in reports.iterrows()
}

model_names = list(model_dir_dict.keys())
probs = df[model_names].values          # shape (n, n_submodels)
w = np.array([weights[m] for m in model_names])
consensus = (probs * w).sum(axis=1) / w.sum()
```

4. **Output columns** in this order: `consensus_score`, then one column per sub-model.

| column | description |
|--------|-------------|
| `consensus_score` | quality-weighted average of all sub-model probabilities |
| `individual_inhibition` | probability from sub-model trained on individual inhibition assay (e.g. CHEMBL4296188 for abaumannii) |
| `merged_mic_decoys` | probability from sub-model trained on merged MIC data with decoys |
| `general_mic` | probability from sub-model trained on general MIC data |
| `general_activity_decoys` | probability from sub-model trained on general % activity data |
| `general_mic50` | probability from sub-model trained on general MIC50 data |

(Drop any rows that don't apply to the pathogen.)

### iii.3 — run_columns.csv

Reflect the same set of columns produced by `main.py`. Template (adapt the pathogen name in the descriptions):

```csv
name,type,direction,description
consensus_score,float,high,Quality-weighted consensus probability of antimicrobial activity against {full pathogen name} (0-1)
individual_inhibition,float,high,Probability of antimicrobial activity from model trained on individual inhibition assay data
merged_mic_decoys,float,high,Probability of antimicrobial activity from model trained on merged MIC measurements
general_mic,float,high,Probability of antimicrobial activity from model trained on general MIC data
general_activity_decoys,float,high,Probability of antimicrobial activity from model trained on general percentage inhibition data
general_mic50,float,high,Probability of antimicrobial activity from model trained on general MIC50 data
```

### iii.4 — metadata.yml

Fill in the template (edit the existing file in eosXXXX). Per-pathogen fields to adapt: `Identifier`, `Slug`, `Title`, `Description`, `Output Dimension`, `Interpretation`, `Tag`, `Target Organism`. Other fields are stable across pathogens.

```yaml
Identifier: eosXXXX
Slug: antimicrobial-activity-{pathogen}
Status: In progress
Title: Prediction of antimicrobial activity against {Full pathogen name} from public bioactivity data
Description: >
  QSAR model scoring the likelihood of antimicrobial activity against {Full pathogen
  name} from publicly available ChEMBL bioactivity data. Independent models are
  trained on multiple bioactivity endpoints using LazyQSAR
  (ersilia-os/chembl-antimicrobial-tasks, ersilia-os/chembl-antimicrobial-models),
  returning one score per endpoint alongside a combined consensus score.
Deployment:
  - Local
  - Online
Source: Local, Online
Source Type: Internal
Task: Annotation
Subtask: Activity prediction
Input:
  - Compound
Input Dimension: 1
Output:
  - Score
Output Dimension: <1 + number of sub-models>
Output Consistency: Fixed
Interpretation: >
  Scores between 0 and 1. Higher values indicate higher predicted likelihood of
  antimicrobial activity against {Full pathogen name}. The first column
  (consensus_score) is a quality-weighted average across all sub-models.
  The remaining columns correspond to individual sub-models trained on different
  ChEMBL bioactivity endpoints.
Tag:
  - {Short tag, e.g. A.baumannii}
  - {ESKAPE if applicable}
  - Antimicrobial activity
  - ChEMBL
Biomedical Area:
  - Infectious disease
  - Antimicrobial resistance
Target Organism: {Full pathogen name}
Publication Type: Other
Publication Year: 2025
Publication: None
Source Code: https://github.com/ersilia-os/chembl-antimicrobial-models
License: GPL-3.0-or-later
Contributor: arnaucoma24
```

### iii.5 — install.yml

Dependencies needed (pin all versions; same across all pathogens):

```yaml
python: "3.10"
commands:
  - ["pip", "lazyqsar", "<version>"]
  - ["pip", "numpy", "1.26.4"]
  - ["pip", "pandas", "2.0.3"]
  - ["pip", "onnxruntime", "<version>"]
  - ["pip", "ersilia-pack-utils", "0.1.5"]
```

Check the exact lazyqsar and onnxruntime versions used in `chembl-antimicrobial-models`.

### iii.6 — Example files

`model/framework/examples/run_input.csv`: 3 SMILES, one per row, header = `smiles`.
Use known active compounds against the pathogen from the training set if possible.

`model/framework/examples/run_output.csv`: run `main.py` on `run_input.csv` to generate this.
Must match exactly what the model produces.

---

## Step iv — Pull request

Once all files are in place and tested locally:

```bash
cd /path/to/eosXXXX
git add .
git commit -m "Add {pathogen} antimicrobial activity model"
git push origin main
gh pr create --repo ersilia-os/eosXXXX \
  --title "Add antimicrobial activity model for {Full pathogen name}" \
  --body "..."
```

The PR triggers automated tests (GitHub Actions in eosXXXX). Fix any failures before merging. Once merged and workflows are green on the merged commit, delete the `arnaucoma24/eosXXXX` fork (step v) and update the monitoring table.

---

## Per-pathogen variability — what to change

Across pathogens, only these things change:

- `PATH_TO_CAMM/output/results/09_models/{pathogen}/` → checkpoints
- `reports.csv` → filter `10_reports.csv` to that pathogen's rows
- **Number of sub-models** (and therefore output columns and `model_dir_dict` keys) varies per pathogen
- Slug, title, description, organism tag, target organism
- Data sources mention (ChEMBL only vs ChEMBL + PubChem)
- eos ID (assigned when the GitHub issue is approved)

Issues for the remaining pathogens can be created programmatically via `gh issue create` using the refined template from the abaumannii issue (#1849).
