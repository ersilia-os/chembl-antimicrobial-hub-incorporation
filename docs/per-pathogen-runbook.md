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
| `cam-models-runtime` | **3.12** | Shared model runtime: lazyqsar==3.3.0 + CPU torch + chemprop/rdkit/FPSim2 + descriptor weights (chemeleon/clamp/cddd subset) + ersilia-pack-utils. Built once from one fork's `install.yml`, reused across all 15 forks | one fork's `install.yml` (built once, then reused; `03_test_pathogen.py` runs `lazyqsar setup --only …` per-pathogen on demand) | only to run `bash run.sh` against any fork |

Why Python 3.12 in the model env: `chemprop==2.2.3` (installed by `lazyqsar setup`) requires Python ≥3.11. Always pin `python: "3.12"` in `install.yml`.

Why `pip install lazyqsar==3.3.0` (NOT `lazyqsar[descriptors]`): the `[descriptors]` extra would resolve `torch>=2.6.0` against PyPI's default index, pulling the CUDA wheel + ~3 GB of `nvidia-*` libs that pip won't auto-remove later. Skipping the extra leaves the env torch-free until `lazyqsar setup --descriptors` runs, which then installs torch from PyTorch's CPU index. Final env is ~2.7 GB instead of ~7 GB.

Why [v3.3.0](https://github.com/ersilia-os/lazy-qsar/releases/tag/v3.3.0): first PyPI release after the v3.2.x line. Carries forward the post-3.2.1 fixes: lazy imports of `xgboost`/`sklearn`/`joblib` ([lazy-qsar#31](https://github.com/ersilia-os/lazy-qsar/issues/31)), `--only` flag + `download_clamp()` ([lazy-qsar#33](https://github.com/ersilia-os/lazy-qsar/issues/33)), matplotlib `MPLCONFIGDIR` isolation ([lazy-qsar#30](https://github.com/ersilia-os/lazy-qsar/issues/30)), MergeShapeInfo ONNX warning suppression ([lazy-qsar#34](https://github.com/ersilia-os/lazy-qsar/issues/34)), and the in-memory `predict(smiles=…)` API.

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

One ignore: `model/framework/fit/` — we don't ship training pipeline contents. Descriptor weights live in `$HOME/.lazyqsar/`, never in the model tree.

```
# Sub-models under model/checkpoints/models/ and model/checkpoints/reports.csv
# ship via regular git. Descriptor weights live in $HOME/.lazyqsar/ — they are
# downloaded at install time by `lazyqsar setup` and never committed here.
model/framework/fit/*
!model/framework/fit/.gitkeep
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
└── reports.csv                           ← {pathogen} rows from $PATH_TO_CAMM/output/results/10_reports.csv
```

Why `models/` as a sub-folder: keeps the per-pathogen QSAR models cleanly separated from the reports.csv.

Where descriptor weights go: lazyqsar reads them from `$HOME/.lazyqsar/`. `lazyqsar setup --descriptors --only …` (from `install.yml`) downloads the per-pathogen subset there at Hub install time. main.py imports lazyqsar without overriding HOME. Locally, `03_test_pathogen.py` runs the same setup on demand if files are missing.

Commands (assuming `cam-hub-inc` is active):

```bash
PATHOGEN={pathogen}
CKPT=$(pwd)/model/checkpoints

# 1. Copy all sub-models present for this pathogen
mkdir -p $CKPT/models
for m in $(ls $PATH_TO_CAMM/output/results/09_models/$PATHOGEN/); do
  cp -r $PATH_TO_CAMM/output/results/09_models/$PATHOGEN/$m $CKPT/models/
done

# 2. reports.csv — pathogen subset only
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

1. **Import lazyqsar directly.** Descriptor weights live in `$HOME/.lazyqsar/` (lazyqsar's default cache), populated by `lazyqsar setup` at install time. No HOME override needed in main.py:

   ```python
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
    - ["pip", "ersilia-pack-utils", "0.1.5"]
    - ["pip", "lazyqsar", "3.3.0"]
    - "lazyqsar setup --descriptors --only chemeleon,clamp"
```

For pathogens that also use cddd (e.g. mtuberculosis), the third line becomes `--only chemeleon,clamp,cddd`.

Each line in order:
1. `ersilia-pack-utils==0.1.5` — Ersilia Hub I/O conventions (`read_smiles`, `write_out`).
2. `lazyqsar==3.3.0` — base install ONLY (no `[descriptors]` extra). The extras would pull `torch>=2.6.0` from PyPI = CUDA wheel + ~3 GB of `nvidia-*` libs that pip won't garbage-collect later. Base install ships no torch.
3. `lazyqsar setup --descriptors --only …` — `install_torch()` pip-installs torch from PyTorch's CPU index (no torch is installed yet, so this lands CPU torch fresh — CUDA never enters the env). Setup also pip-installs chemprop / rdkit / FPSim2 and downloads the per-pathogen descriptor weights (~34 MB chemeleon + ~167 MB clamp; cddd adds ~415 MB) into `$HOME/.lazyqsar/`.

Important gotchas (don't repeat these):
- Don't use `python: "3.10"` — chemprop 2.2.3 requires ≥ 3.11.
- Don't add the `[descriptors]` extra to the pip install line — it would pull CUDA torch and ~3 GB of `nvidia-*` transitive deps. Stick with `pip install lazyqsar==3.3.0` (no extras) so torch is only installed later by `lazyqsar setup` from PyTorch's CPU index.
- Don't bundle the descriptor weights inside the model tree — they live in `$HOME/.lazyqsar/` and are downloaded by `lazyqsar setup` at install time.
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
        model/framework/fit/.gitkeep \
        model/checkpoints/              # ~50 MB; regular git
git commit -m "Add antimicrobial activity model for {Full pathogen name}"
git push origin main

gh pr create --repo ersilia-os/{eosXXXX} \
  --title "Add antimicrobial activity model for {Full pathogen name}" \
  --body "$(cat <<'EOF'
Related to ersilia-os/ersilia#<issue-number>.

Packages the {Full pathogen name} QSAR sub-models from ersilia-os/chembl-antimicrobial-models into a single Hub model.

- Output: 1 + N columns (\`consensus_score\` + per-sub-model probabilities).
- Consensus: W1-W7 + W8 quality-weighted average + tanh IQR-restoring transform, mirroring \`chembl-antimicrobial-models/scripts/14_consensus_scoring.py\`.
- Sub-model checkpoints ship in regular git; descriptor weights are downloaded at install time by \`lazyqsar setup --descriptors\` into `$HOME/.lazyqsar/`.
- Tested locally on Python 3.12 with \`lazyqsar==3.3.0\` (no \`[descriptors]\` extra, to avoid CUDA torch).

Per-pathogen procedure documented at https://github.com/ersilia-os/chembl-antimicrobial-hub-incorporation/blob/main/docs/per-pathogen-runbook.md.
EOF
)"
```

This matches `scripts/04_publish_pathogen.py`'s `PR_BODY_TEMPLATE` — keep them in sync if you edit either.

Verify in the PR:
- `model/checkpoints/models/` is populated with the sub-models (plain git — no LFS pointers).
- `model/checkpoints/reports.csv` is the pathogen-filtered subset.
- `model/checkpoints/` does NOT contain a `featurizer_weights_home/` dir (descriptor weights live in `$HOME/.lazyqsar/`).
- `run_output.csv` matches the regeneration exactly.

Update the coordinator's [monitoring table](../CLAUDE.md#monitoring-table): "model prepared" → True; once the PR merges, "PR merged" → True.

---

## Step 8 — Tear down the fork and local clone

After merge, delete both the GitHub fork AND the local clone:

```bash
gh repo delete arnaucoma24/{eosXXXX} --yes
rm -rf {eosXXXX}
```

Then in the coordinator's monitoring table: "cleaned up" → True.

---

## Step 9 — Confirm post-merge workflows are green

Once merged, the model test workflows run on the `ersilia-os/{eosXXXX}` main branch:

```bash
gh run list --repo ersilia-os/{eosXXXX} --limit 5
```

When all are green, "workflows passed" → True in the monitoring table.

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
| `.gitignore` | **drop** `model/checkpoints/*` (sub-models ship in regular git); keep `model/framework/fit/*` ignore. No `featurizer_weights_home/` entry — descriptor weights live in `$HOME/.lazyqsar/` |
| `install.yml` | **rewrite** to `ersilia-pack-utils` + `lazyqsar==3.3.0` (NO `[descriptors]` extra) + `lazyqsar setup --descriptors --only <per-pathogen-list>`, python 3.12 |
| `metadata.yml` | **edit each field** (template ships placeholders) |
| `model/checkpoints/models/<sub_model>/…` | **populate** from `$PATH_TO_CAMM/output/results/09_models/{pathogen}/` |
| `model/checkpoints/reports.csv` | **filter** `$PATH_TO_CAMM/output/results/10_reports.csv` to this pathogen's rows |
| `model/framework/code/main.py` | **rewrite** (template placeholder computes MolWt). Reads MODEL_NAMES from `run_columns.csv` at runtime — no hardcoded list. |
| `model/framework/code/consensus.py` | **copy verbatim** from any sibling fork — quality-weighted consensus math, identical across all 15 pathogens |
| `model/framework/columns/run_columns.csv` | **fill** with `1 + n_submodels` rows following the factual-only style. Order matters — main.py uses this file's row order as the authoritative MODEL_NAMES. |
| `model/framework/examples/run_input.csv` | **fill** with 3 SMILES from `$PATH_TO_CAMM/output/results/03_selected_positives.csv` filtered to this pathogen |
| `model/framework/examples/run_output.csv` | **generate** by running `bash run.sh` against the input |

---

## Reused references — don't reinvent these

- Consensus math (W1–W8 + tanh): [`$PATH_TO_CAMM/scripts/14_consensus_scoring.py`](../../chembl-antimicrobial-models/scripts/14_consensus_scoring.py), lines 55–97. Copy the structure into `main.py` verbatim.
- LazyQSAR multi-model `predict` call pattern: [`$PATH_TO_CAMM/scripts/12_predict_drugbank.py`](../../chembl-antimicrobial-models/scripts/12_predict_drugbank.py), lines 31–37 (HOME env trick) and 124–134 (call signature).
- Ersilia metadata template guide: https://ersilia.gitbook.io/ersilia-book/ersilia-model-hub/model-contribution/model-template.
- Reference filled model (abaumannii): [../eos21dr/](../eos21dr/) in this repo.
