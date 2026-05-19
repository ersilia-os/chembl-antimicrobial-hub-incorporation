# Per-pathogen Ersilia model packaging runbook

End-to-end procedure for taking one pathogen's QSAR sub-models from `chembl-antimicrobial-models` (CAMM) and shipping them as a single Ersilia Model Hub entry (`eosXXXX`). Validated on **abaumannii / eos21dr** (2026-05-16).

For high-level orientation and the cross-pathogen monitoring table, see [../CLAUDE.md](../CLAUDE.md).

---

## Conventions

- `{pathogen}` — short code from the CLAUDE.md monitoring table (`abaumannii`, `efaecium`, …).
- `{eosXXXX}` — the EOS identifier assigned by Ersilia when the model-request issue is approved (e.g. `eos21dr` for abaumannii).
- `$PATH_TO_CAMM` — your local clone of `ersilia-os/chembl-antimicrobial-models`. Always export at the top of a session:

  ```bash
  export PATH_TO_CAMM=/aloy/home/acomajuncosa/Ersilia/chembl-antimicrobial-models
  ```

- All work for one pathogen happens inside `./{eosXXXX}/` at the root of this coordinator repo. That directory is gitignored by the coordinator and has its own git history pointing to `arnaucoma24/{eosXXXX}`.

---

## Two conda environments

We use two clearly separated envs. **Never collapse them.**

| Env | Python | Purpose | Created from | When to use |
|-----|--------|---------|--------------|-------------|
| `cam-hub-inc` | 3.10 | Coordinator: filtering reports.csv, gh, helper scripts | manual (`conda create … python=3.10`) | for tasks driven from the coordinator repo |
| `cam-models-runtime` | **3.12** | Shared model runtime: CPU torch + lazyqsar[descriptors]@42ab866 + descriptor weights (chemeleon/clamp/cddd subset) + ersilia-pack-utils. Built once from one fork's `install.yml`, reused across all 15 forks | one fork's `install.yml` (built once, then reused; `03_test_pathogen.py` runs `lazyqsar setup --only … --target-dir <fork>/…` per-pathogen on demand) | only to run `bash run.sh` against any fork |

Why Python 3.12 in the model env: `lazyqsar[descriptors]` transitively requires `chemprop==2.2.3`, which requires Python ≥3.11. Always pin `python: "3.12"` in `install.yml`.

Why **CPU torch first**: the CUDA torch wheel pulls ~3 GB of NVIDIA libraries we don't need. Install CPU torch from `https://download.pytorch.org/whl/cpu` BEFORE `lazyqsar[descriptors]`, which then sees `torch>=2.6.0` already satisfied and skips its own pull. Final env is ~2.7 GB (vs ~7 GB with CUDA torch).

Why `lazyqsar[descriptors]@<commit>` (not `[all]`, not `[descriptors]==3.2.1`): commit `42ab866` is the post-3.2.1 main HEAD that includes:
- [lazy-qsar#31](https://github.com/ersilia-os/lazy-qsar/issues/31) — lazy imports of `xgboost`/`sklearn`/`joblib`, so `[descriptors]` alone is now sufficient for inference (was `ModuleNotFoundError: xgboost` before).
- [lazy-qsar#33](https://github.com/ersilia-os/lazy-qsar/issues/33) — `lazyqsar setup --descriptors` gains `--only` and `--target-dir` flags, plus `download_clamp()`.
- SMILES validation refactor (5× speedup on validation for large batches).

Switch to a tagged release once one cuts (likely `v3.2.2`).

---

## Step 0 — Create the model-request issue & clone the fork

1. Open a Model Request issue at `ersilia-os/ersilia` with the pathogen's name and a draft description (see Miquel's wording style in step 5). Once approved, an `eosXXXX` ID is assigned and `ersilia-os/{eosXXXX}` is auto-created.
2. Fork `ersilia-os/{eosXXXX}` to `arnaucoma24/{eosXXXX}` via GitHub UI.
3. Clone the fork **into this coordinator repo** (the coordinator's `.gitignore` already excludes `eos*/`):

   ```bash
   cd /aloy/home/acomajuncosa/Ersilia/chembl-antimicrobial-hub-incorporation
   git clone git@github.com:arnaucoma24/{eosXXXX}.git
   cd {eosXXXX}
   ```

4. The Ersilia template ships with a placeholder `mock.txt`. Delete it:

   ```bash
   git rm mock.txt
   ```

5. Update the coordinator's [monitoring table](../CLAUDE.md#monitoring-table): set "forked to arnaucoma24" → True, paste the issue link.

---

## Step 1 — Checkpoints (regular git)

Everything under `model/checkpoints/` ships in plain git — no Git LFS, no eosvc. The sub-models are ~50 MB per pathogen, well within GitHub's recommended repo size. Descriptor weights (~200-615 MB) are NOT in the repo; they're downloaded at install time by `lazyqsar setup` (see Step 4).

### 1a. `.gitignore`

Two ignores:
1. `model/framework/fit/` — we don't ship training pipeline contents.
2. `model/checkpoints/featurizer_weights_home/` — descriptor weights are downloaded at install time, not committed.

```
# Sub-models under model/checkpoints/models/ and model/checkpoints/reports.csv
# ship via regular git. featurizer_weights_home/ is populated at install time
# by `lazyqsar setup` (see install.yml) and is not committed.
model/framework/fit/*
!model/framework/fit/.gitkeep

# Descriptor weights are downloaded at install time by `lazyqsar setup
# --descriptors --only … --target-dir …` (see install.yml). Don't commit
# the downloaded artifacts.
model/checkpoints/featurizer_weights_home/*
!model/checkpoints/featurizer_weights_home/.gitkeep
```

### 1b. Populate `model/checkpoints/`

Final layout we want (~50 MB total per pathogen — sub-models only; the descriptor weights are downloaded at install time, not bundled). Everything below ships in regular git:

```
{eosXXXX}/model/checkpoints/
├── .gitkeep
├── models/                              ← all QSAR sub-models for this pathogen
│   ├── individual_inhibition/
│   ├── merged_mic_decoys/
│   ├── general_mic/
│   ├── general_activity_decoys/
│   ├── general_mic50/
│   └── …                                 ← the set varies per pathogen
├── featurizer_weights_home/.gitkeep     ← placeholder so the dir survives a clean clone;
│                                          contents are downloaded by `lazyqsar setup`
│                                          at install time (see Step 4)
└── reports.csv                           ← {pathogen} rows from $PATH_TO_CAMM/output/results/10_reports.csv
```

Why `models/` as a sub-folder: keeps the per-pathogen QSAR models cleanly separated from the descriptor weights and the reports.csv.

Why `featurizer_weights_home/.lazyqsar/` (populated at install time, not now): lazyqsar locates its featurizer weights at `$HOME/.lazyqsar/`. In `main.py` we set `os.environ["HOME"] = .../checkpoints/featurizer_weights_home` so this folder satisfies that lookup. The descriptor weights themselves (~200-615 MB depending on pathogen) are NOT bundled in the repo — gitignored. `lazyqsar setup --descriptors --only … --target-dir model/checkpoints/featurizer_weights_home/.lazyqsar` (from `install.yml`) downloads them at Hub install time. Locally, `03_test_pathogen.py` runs the same command on demand if files are missing.

Commands (assuming `cam-hub-inc` is active):

```bash
PATHOGEN={pathogen}
CKPT=$(pwd)/model/checkpoints

# 1. Copy all sub-models present for this pathogen
mkdir -p $CKPT/models
for m in $(ls $PATH_TO_CAMM/output/results/09_models/$PATHOGEN/); do
  cp -r $PATH_TO_CAMM/output/results/09_models/$PATHOGEN/$m $CKPT/models/
done

# 2. Featurizer weights placeholder
mkdir -p $CKPT/featurizer_weights_home
touch $CKPT/featurizer_weights_home/.gitkeep

# 3. reports.csv — pathogen subset only
python3 -c "
import pandas as pd
df = pd.read_csv('$PATH_TO_CAMM/output/results/10_reports.csv')
df[df.pathogen=='$PATHOGEN'].to_csv('$CKPT/reports.csv', index=False)
print(df[df.pathogen=='$PATHOGEN'][['model_name','decision_cutoff_rank']])
"
```

Verify before continuing: `du -sh $CKPT/` should be on the order of ~50 MB (sub-models + reports.csv only — descriptor weights are downloaded at install time, not bundled); `ls $CKPT/models/` should list every sub-model directory that exists for the pathogen in `09_models/`.

---

## Step 2 — `main.py`

Replace the template scaffolding at `{eosXXXX}/model/framework/code/main.py` with the LazyQSAR + consensus inference pipeline. The abaumannii implementation lives at [eos21dr/model/framework/code/main.py](../eos21dr/model/framework/code/main.py) — clone its structure and **edit only `MODEL_NAMES` per pathogen**.

Key invariants that apply to every pathogen:

1. **Set `HOME` *before* importing lazyqsar.** lazyqsar caches the value at import time:

   ```python
   os.environ["HOME"] = os.path.join(checkpoints, "featurizer_weights_home")
   from lazyqsar.api.classifier_predict import predict as lqsar_predict
   ```

2. **Call `lqsar_predict` once with the full `model_dir` dict** — descriptors are shared across sub-models, which saves both time and memory vs. calling it once per sub-model:

   ```python
   model_dir_dict = {m: os.path.join(checkpoints, "models", m) for m in MODEL_NAMES}
   lqsar_predict(model_dir=model_dir_dict, input_csv=..., output_csv=..., predict_type="rank")
   ```

   `predict_type="rank"` is **always** correct, even though the values are calibrated probability-like scores and not batch-relative ranks. The training repo's `scripts/12_predict_drugbank.py` and `scripts/14_consensus_scoring.py` both consume these "rank" values directly as probabilities.

3. **Consensus follows `chembl-antimicrobial-models/scripts/14_consensus_scoring.py`.** Uses W1–W7 (model-level quality weights from reports.csv) **plus W8** (per-compound weight from `decision_cutoff_rank` — 0 at or below cutoff, linear 0→1 above). All 8 weights are averaged with uniform weights `np.ones(8)`, then a tanh transform restores the IQR:

   ```
   k(M) = 2·(1 + 1.156·(1 - exp(-M/6.47)))   # M = number of sub-models
   consensus = 0.5 + 0.5·tanh(k·(raw - 0.5)) / tanh(k/2)
   ```

   The plain CLAUDE.md guidance that says "use W1–W7 only, skip W8" is **wrong** — keep W8.

4. **Output column order**: `consensus_score, <sub_model_1>, <sub_model_2>, …`. Sub-models follow the order in your `MODEL_NAMES` list. The pre-tanh raw consensus is computed as an intermediate but **not** written to the output.

---

## Step 3 — `run_columns.csv`

`{eosXXXX}/model/framework/columns/run_columns.csv`. Header is `name,type,direction,description`. All rows have `type=float`, `direction=high`.

**Description style (strict)**: Factual, one line per column. Mention the *training data* and *cutoff* and *n*. **Never include interpretation language** — no "higher = more likely active", no "0-1 range", no "relative to input batch" caveats. Direction `high` and the `metadata.yml` `Interpretation` field already convey that meaning.

Canonical phrasing (golden example for the sub-model rows):

```
Probability from sub-model trained on MIC measurements aggregated across 2075 ChEMBL assays (cutoff 10 uM; n=7763).
```

For the consensus row:

```
Tanh-transformed quality-weighted consensus probability across the N sub-models.
```

Where to find the assay/cutoff/n details for a pathogen: `$PATH_TO_CAMM/output/results/07_datasets_metadata.csv`. Each row there names the sub-model (via `name` and `label`) and gives `cutoff`, `unit`, `activity_type`, `n_assays`, and `final_compounds`.

For abaumannii's complete file see [eos21dr/model/framework/columns/run_columns.csv](../eos21dr/model/framework/columns/run_columns.csv).

---

## Step 4 — `install.yml`

`{eosXXXX}/install.yml`. The `--only` list of descriptors is **per-pathogen** — `02_init_pathogen.py` scans the sub-model dirs and derives it from which featurizer subdirectories (`chemeleon/`, `clamp/`, `cddd/`) actually appear. abaumannii's install.yml:

```yaml
python: "3.12"
commands:
    - ["pip", "torch", "2.6.0", "--index-url", "https://download.pytorch.org/whl/cpu"]
    - "pip install lazyqsar[descriptors]@git+https://github.com/ersilia-os/lazy-qsar.git@42ab866"
    - "lazyqsar setup --descriptors --only chemeleon,clamp --target-dir model/checkpoints/featurizer_weights_home/.lazyqsar"
    - ["pip", "ersilia-pack-utils", "0.1.5"]
```

For pathogens that also use cddd (e.g. mtuberculosis), the third line becomes `--only chemeleon,clamp,cddd`.

Order matters:
1. **CPU torch FIRST** so the subsequent `lazyqsar[descriptors]` install sees `torch>=2.6.0` already satisfied and won't pull the default PyPI CUDA wheel (~3 GB of NVIDIA libs we don't need). Final env is ~2.7 GB instead of ~7 GB.
2. `lazyqsar[descriptors]@git+…@42ab866` — pinned to the post-3.2.1 commit on `main` that ships lazy imports for `xgboost`/`sklearn`/`joblib` (so `[descriptors]` alone now works for inference, fixes [lazy-qsar#31](https://github.com/ersilia-os/lazy-qsar/issues/31)), plus the `--only` / `--target-dir` setup flags + `download_clamp()` (fixes [lazy-qsar#33](https://github.com/ersilia-os/lazy-qsar/issues/33)), plus a SMILES-validation refactor (5× speedup on validation for large batches). Switch to a tagged release once one cuts (likely `v3.2.2`). Written as a raw string (not a list) because `ersilia-pack`'s YAML install parser rejects 2-element `["pip", "<spec>"]` lists — it treats the 3rd element of any `["pip", ...]` list as a version, so PEP 508 direct references (`pkg @ git+url`) only work in the string form.
3. `lazyqsar setup --descriptors --only … --target-dir …` materialises just the descriptor weights this pathogen needs (~34 MB chemeleon + ~167 MB clamp + optional ~415 MB cddd) into the fork's checkpoint tree at install time. The weights are NOT bundled in the repo — gitignored.
4. `ersilia-pack-utils==0.1.5` — Ersilia Hub I/O conventions.

Important gotchas (don't repeat these):
- Don't use `python: "3.10"` — chemprop 2.2.3 requires ≥ 3.11.
- Don't drop the `--index-url https://download.pytorch.org/whl/cpu` flag — the default PyPI torch wheel pulls ~3 GB of CUDA libraries.
- Don't bundle the descriptor weights in `model/checkpoints/featurizer_weights_home/.lazyqsar/` — they're meant to be downloaded by `lazyqsar setup` at install time. The directory is gitignored except for `.gitkeep`.
- Don't bother pinning numpy/pandas/onnxruntime/rdkit explicitly — let lazyqsar's pyproject pin them transitively.

---

## Step 5 — `metadata.yml`

`{eosXXXX}/metadata.yml`. Per-pathogen fields to fill: `Identifier`, `Slug`, `Title`, `Description`, `Output Dimension`, `Tag` (pathogen short tag), `Target Organism`. Most other fields are fixed across the family.

### Controlled vocabularies — check before filling

Three fields draw from a closed list. **If your pathogen isn't in the list, append it to the source-of-truth file in ersilia-os/ersilia before committing.**

| Field | Controlled-vocab file |
|-------|----------------------|
| `Tag` | [`ersilia/hub/content/metadata/tag.txt`](https://github.com/ersilia-os/ersilia/blob/main/ersilia/hub/content/metadata/tag.txt) |
| `Biomedical Area` | [`ersilia/hub/content/metadata/biomedical_area.txt`](https://github.com/ersilia-os/ersilia/blob/main/ersilia/hub/content/metadata/biomedical_area.txt) |
| `Target Organism` | [`ersilia/hub/content/metadata/target_organism.txt`](https://github.com/ersilia-os/ersilia/blob/main/ersilia/hub/content/metadata/target_organism.txt) |

For the 15 pathogens in this project all entries already exist in `target_organism.txt`. `biomedical_area.txt` does NOT contain "Infectious disease" — antimicrobial models should use `Antimicrobial resistance` (the only AMR-flavoured biomedical area available).

### Field-by-field

Follow the Ersilia model-template guide (https://ersilia.gitbook.io/ersilia-book/ersilia-model-hub/model-contribution/model-template). Hard rules from there:

- **`Status`** — exactly `In progress` (lowercase p). The gitbook docs say "In Progress" but that's wrong; the validator reads the controlled vocab from [`ersilia/hub/content/metadata/status.txt`](https://github.com/ersilia-os/ersilia/blob/master/ersilia/hub/content/metadata/status.txt), which lists `Test / In maintenance / In progress / Ready / Archived`. The template default `In progress` already passes — leave it alone.
- **`Title`** — single string, **min 70 chars**, self-descriptive.
- **`Description`** — single string, **min 200 chars**, must cover model type, results, training dataset. Use the abaumannii wording as the template (see [eos21dr/metadata.yml](../eos21dr/metadata.yml)) and adapt the organism name. Avoid the word "endpoint"; mention `ChEMBL and PubChem` for pathogens with PubChem data (saureus, ecoli, mtuberculosis, pfalciparum, calbicans) and just `ChEMBL` for the rest.
- **`Interpretation`** — **one brief sentence under 200 chars**. Example from eos3804: `Probability of growth inhibition of the bacteria A. Baumannii (threshold > 80%)`. Don't write paragraphs here — the Hub catalog renders it in a small cell.
- **`Source`** — **single string**, one of `Local` or `Online`. The template ships with `Source: Local, Online` (comma-separated string) which **fails** the schema validator. Set to `Source: Local` (matches eos19mt and eos3804 convention). Do not confuse with `Deployment:`, which IS a list and CAN contain both `Local` and `Online`.
- **Other single-value fields the template ships as comma-strings** — trim to one value: `Source Type: Internal`, `Task: Annotation`, `Subtask: Activity prediction`, `Output: Score`, `Output Consistency: Fixed`, `Publication Type: Other`.
- **`Output Dimension`** — `1 + (number of sub-models for this pathogen)`. For abaumannii (5 sub-models) that's 6.
- **`License`** — SPDX identifier. Use `GPL-3.0-or-later` (matches the training repo).
- **`Publication Type`** — `Other` (no peer-reviewed paper for these models yet).
- **`Publication`** — **must be present** AND a **valid URL**. The validator has a bug ([ersilia/publish/test/services/checks.py:_check_model_publication](https://github.com/ersilia-os/ersilia/blob/master/ersilia/publish/test/services/checks.py)) — omitting the key triggers a `KeyError` ("An unexpected exception occurred: 'Publication'"); leaving `Publication: None` triggers `EmptyField`. With no peer-reviewed paper, use the Source Code URL as a placeholder: `Publication: https://github.com/ersilia-os/chembl-antimicrobial-models`.

Reference: abaumannii's filled metadata is at [eos21dr/metadata.yml](../eos21dr/metadata.yml).

### Edit, don't overwrite

Use the `Edit` tool (or manual diff edits) instead of `Write` — the user prefers to see metadata changes as diffs against the Ersilia template defaults rather than as wholesale rewrites. This makes it easy to spot if a placeholder slipped through.

---

## Step 6 — Example files

### `model/framework/examples/run_input.csv`

Header `smiles`, then **3 SMILES, one per row**. The best source is the training set's positives:

```bash
source ~/programs/miniconda3/etc/profile.d/conda.sh && conda activate cam-hub-inc
python3 -c "
import pandas as pd
df = pd.read_csv('$PATH_TO_CAMM/output/results/03_selected_positives.csv')
hits = df[df['found_in'].str.contains('{pathogen}', na=False)]
hits = hits[hits['smiles'].str.len().between(30, 80)]
print(hits[['smiles','found_in']].head(5).to_string(index=False))
"
```

Pick 3 with diverse structures. SMILES of 30-80 chars keep the example file readable.

### `model/framework/examples/run_output.csv`

**Never hand-write this.** It must be byte-identical to what `bash run.sh` produces — Ersilia's CI compares them. Generate it:

```bash
conda activate cam-models-runtime    # shared model env, Python 3.12
cd {eosXXXX}

bash model/framework/run.sh model/framework \
     model/framework/examples/run_input.csv \
     model/framework/examples/run_output.csv

cat model/framework/examples/run_output.csv     # spot-check
```

Expected: 1 header + 3 data rows, each with `1 + n_submodels` columns, all values in `[0,1]`.

Two harmless warnings you can ignore:
- `CUDA initialization: The NVIDIA driver on your system is too old` — torch tries CUDA, falls back to CPU.
- `MergeShapeInfo … Falling back to lenient merge` — ONNX shape-inference warning; output is still correct.

---

## Step 7 — Commit, PR, merge

Inside `{eosXXXX}/`:

```bash
git add .gitignore install.yml metadata.yml \
        model/framework/code/main.py \
        model/framework/columns/run_columns.csv \
        model/framework/examples/run_input.csv \
        model/framework/examples/run_output.csv \
        model/checkpoints/              # ~50 MB; regular git
git commit -m "Add antimicrobial activity model for {Full pathogen name}"
git push origin main

gh pr create --repo ersilia-os/{eosXXXX} \
  --title "Add antimicrobial activity model for {Full pathogen name}" \
  --body "Related to ersilia-os/ersilia#<issue-number>. Built from ersilia-os/chembl-antimicrobial-models."
```

Verify in the PR:
- `model/checkpoints/models/` is populated with the sub-models (plain git — no LFS pointers).
- `model/checkpoints/reports.csv` is the pathogen-filtered subset.
- `model/checkpoints/featurizer_weights_home/` contains only `.gitkeep`.
- `run_output.csv` matches the regeneration exactly.

Update the coordinator's [monitoring table](../CLAUDE.md#monitoring-table): "model prepared" → True; once Ersilia CI passes and merges, "PR merged" → True and "workflows passed" → True.

---

## Step 8 — Tear down the fork

After merge + CI green, delete the personal fork (or at least mark it archived):

```bash
gh repo delete arnaucoma24/{eosXXXX} --yes
```

Then in the coordinator's monitoring table: "fork removed" → True.

---

## End-to-end verification checklist

Before opening the PR:

- [ ] `du -sh {eosXXXX}/model/checkpoints/` is ~50 MB (sub-models + reports.csv only — featurizer weights are downloaded at install time).
- [ ] `git lfs ls-files` is empty (we don't use LFS).
- [ ] `head -1 model/framework/examples/run_output.csv` column list matches `cut -d, -f1 model/framework/columns/run_columns.csv | tail -n+2 | tr '\n' ','`.
- [ ] All values in `run_output.csv` are in `[0,1]`.
- [ ] Regenerating `run_output.csv` from `run_input.csv` produces a byte-identical file (no diff).
- [ ] `metadata.yml` fields all use controlled vocabularies (Tag, Biomedical Area, Target Organism).
- [ ] Title ≥ 70 chars; Description ≥ 200 chars; Interpretation < 200 chars.
- [ ] `Output Dimension` equals the actual number of columns in `run_output.csv`.

---

## File-by-file diff against the Ersilia template

When you scaffold a new fork from the Ersilia template you only need to change/create these files. Anything else (LICENSE, README.md, `.github/`, `model/framework/run.sh`, `model/framework/fit/**`) stays as the template ships it.

| Path | Action |
|------|--------|
| `mock.txt` | **delete** (placeholder from the template) |
| `.gitignore` | **drop** `model/checkpoints/*` (sub-models ship in regular git); add `model/checkpoints/featurizer_weights_home/*` with `.gitkeep` exception (descriptor weights downloaded at install time); keep `model/framework/fit/*` ignore |
| `install.yml` | **rewrite** to CPU torch + lazyqsar[descriptors]@42ab866 + `lazyqsar setup --only <per-pathogen-list> --target-dir model/checkpoints/featurizer_weights_home/.lazyqsar` + ersilia-pack-utils, python 3.12 |
| `metadata.yml` | **edit each field** (template ships placeholders) |
| `model/checkpoints/models/<sub_model>/…` | **populate** from `$PATH_TO_CAMM/output/results/09_models/{pathogen}/` |
| `model/checkpoints/featurizer_weights_home/.gitkeep` | **touch** placeholder; descriptor weights are downloaded by `lazyqsar setup` at install time, not bundled |
| `model/checkpoints/reports.csv` | **filter** `$PATH_TO_CAMM/output/results/10_reports.csv` to this pathogen's rows |
| `model/framework/code/main.py` | **rewrite** (template placeholder computes MolWt) |
| `model/framework/columns/run_columns.csv` | **fill** with `1 + n_submodels` rows following the factual-only style |
| `model/framework/examples/run_input.csv` | **fill** with 3 SMILES from `$PATH_TO_CAMM/output/results/03_selected_positives.csv` filtered to this pathogen |
| `model/framework/examples/run_output.csv` | **generate** by running `bash run.sh` against the input |

---

## Reused references — don't reinvent these

- Consensus math (W1–W8 + tanh): [`$PATH_TO_CAMM/scripts/14_consensus_scoring.py`](../../chembl-antimicrobial-models/scripts/14_consensus_scoring.py), lines 55–97. Copy the structure into `main.py` verbatim.
- LazyQSAR multi-model `predict` call pattern: [`$PATH_TO_CAMM/scripts/12_predict_drugbank.py`](../../chembl-antimicrobial-models/scripts/12_predict_drugbank.py), lines 31–37 (HOME env trick) and 124–134 (call signature).
- Ersilia metadata template guide: https://ersilia.gitbook.io/ersilia-book/ersilia-model-hub/model-contribution/model-template.
- Reference filled model (abaumannii): [../eos21dr/](../eos21dr/) in this repo.
