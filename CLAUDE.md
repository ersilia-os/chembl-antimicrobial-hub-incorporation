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

| pathogen | issue # | eos id | forked to arnaucoma24 | model prepared | PR merged | cleaned up | workflows passed |
|----------|---------|--------|-----------------------|----------------|-----------|------------|------------------|
| abaumannii    | [#1849](https://github.com/ersilia-os/ersilia/issues/1849) | [eos21dr](https://github.com/ersilia-os/eos21dr) | True  | True  | True  | True  | True  |
| calbicans     | [#1852](https://github.com/ersilia-os/ersilia/issues/1852) | [eos8jx6](https://github.com/ersilia-os/eos8jx6) | True  | True  | True  | True  | True  |
| campylobacter | [#1853](https://github.com/ersilia-os/ersilia/issues/1853) | [eos7iak](https://github.com/ersilia-os/eos7iak) | True  | False | False | False | False |
| ecoli         | [#1854](https://github.com/ersilia-os/ersilia/issues/1854) | [eos5eya](https://github.com/ersilia-os/eos5eya) | True  | False | False | False | False |
| efaecium      | [#1855](https://github.com/ersilia-os/ersilia/issues/1855) | [eos81zy](https://github.com/ersilia-os/eos81zy) | True  | False | False | False | False |
| enterobacter  | [#1856](https://github.com/ersilia-os/ersilia/issues/1856) | [eos9bpi](https://github.com/ersilia-os/eos9bpi) | True  | False | False | False | False |
| hpylori       | [#1857](https://github.com/ersilia-os/ersilia/issues/1857) | [eos9eyo](https://github.com/ersilia-os/eos9eyo) | True  | False | False | False | False |
| kpneumoniae   | [#1858](https://github.com/ersilia-os/ersilia/issues/1858) | [eos6wb7](https://github.com/ersilia-os/eos6wb7) | True  | False | False | False | False |
| mtuberculosis | [#1859](https://github.com/ersilia-os/ersilia/issues/1859) | [eos43d6](https://github.com/ersilia-os/eos43d6) | True  | False | False | False | False |
| ngonorrhoeae  | [#1860](https://github.com/ersilia-os/ersilia/issues/1860) | [eos5qya](https://github.com/ersilia-os/eos5qya) | True  | False | False | False | False |
| paeruginosa   | [#1861](https://github.com/ersilia-os/ersilia/issues/1861) | [eos2e3s](https://github.com/ersilia-os/eos2e3s) | True  | False | False | False | False |
| pfalciparum   | [#1862](https://github.com/ersilia-os/ersilia/issues/1862) | [eos4an7](https://github.com/ersilia-os/eos4an7) | True  | False | False | False | False |
| saureus       | [#1863](https://github.com/ersilia-os/ersilia/issues/1863) | [eos8lcw](https://github.com/ersilia-os/eos8lcw) | True  | False | False | False | False |
| smansoni      | [#1864](https://github.com/ersilia-os/ersilia/issues/1864) | [eos8v1a](https://github.com/ersilia-os/eos8v1a) | True  | False | False | False | False |
| spneumoniae   | [#1865](https://github.com/ersilia-os/ersilia/issues/1865) | [eos5q52](https://github.com/ersilia-os/eos5q52) | True  | False | False | False | False |

Column meanings:
- **issue #** — ID of the model-request issue at `ersilia-os/ersilia` (an `eosXXXX` ID is assigned when the issue is approved).
- **forked to arnaucoma24** — auto-created `ersilia-os/eosXXXX` has been forked to `arnaucoma24/eosXXXX` and cloned locally.
- **model prepared** — checkpoints, `main.py`, `metadata.yml`, `install.yml`, columns and examples all in place and tested locally.
- **PR merged** — pull request from `arnaucoma24/eosXXXX` into `ersilia-os/eosXXXX` is merged.
- **cleaned up** — both the `arnaucoma24/eosXXXX` GitHub fork AND the local `eos*/` clone in this repo have been deleted now that the model lives upstream.
- **workflows passed** — the post-merge GitHub Actions on `ersilia-os/eosXXXX` main branch (model test workflows) are green.

---

## Overall workflow (per pathogen)

| Step | Action |
|------|--------|
| i    | Create GitHub issue at `ersilia-os/ersilia` requesting model incorporation |
| ii   | Once an `eosXXXX` ID is assigned and `ersilia-os/eosXXXX` is auto-created, fork it to `arnaucoma24` and clone locally |
| iii  | Prepare the model (checkpoints, code, metadata.yml) |
| iv   | Open pull request to `ersilia-os/eosXXXX` |
| v    | Once merged, delete the `arnaucoma24/eosXXXX` fork AND the local `eos*/` clone in this repo |
| vi   | Confirm the post-merge GitHub Actions on `ersilia-os/eosXXXX` main are green |

Update the [monitoring table](#monitoring-table) as each step completes.

---

## Per-pathogen runbook

The full step-by-step procedure for steps iii–v lives in **[docs/per-pathogen-runbook.md](docs/per-pathogen-runbook.md)**. Read it (or skim the section you need) at the start of each pathogen. It was distilled from the abaumannii / eos21dr build session on 2026-05-16 and captures every gotcha we hit.

The reference filled model is at [eos21dr/](eos21dr/) — clone its layout and only edit the per-pathogen fields.

---

## Key principles (must-know in every session)

These override the older guidance that may still be sitting in old plans, notebooks, or PR descriptions.

1. **Checkpoints ship via regular git; descriptor weights live in `$HOME/.lazyqsar/`.** Two storage paths, each serving different consumers:
   - **Sub-models** (`model/checkpoints/models/{sub}/…`, ~50–350 MB per pathogen depending on sub-model count after the AUROC>0.7 filter) and `model/checkpoints/reports.csv` → committed to the fork's regular git tree. No eosvc, no Git LFS. The Ersilia template ships a stray `mock.txt` — delete it.
   - **Descriptor weights** (`chemeleon_mp.pt`, `clamp_encoder.onnx`, `cddd_encoder.onnx`, ~34–615 MB depending on which featurizers are used) → NOT in the repo, NOT in the model tree. Downloaded at install time by `lazyqsar setup --descriptors --only <list>` into `$HOME/.lazyqsar/` (lazyqsar's default cache). main.py imports lazyqsar without any HOME override; lazyqsar finds the weights at runtime via `$HOME/.lazyqsar/`. On dev machines, `scripts/03_test_pathogen.py` runs the same setup on demand if files are missing.
   - `.gitignore` should NOT exclude `model/checkpoints/models/`. `fit/` stays ignored. There is no `featurizer_weights_home/` inside the model tree anymore.

2. **Two conda envs, never collapsed.**
   - `cam-hub-inc` (Python 3.10) — coordinator work: filtering `reports.csv`, `gh`, helper scripts.
   - `cam-models-runtime` (Python **3.12**) — shared model runtime, built from the `install.yml` template once and reused across every pathogen. Python 3.12 (not 3.10) because `chemprop==2.2.3` requires ≥3.11.

3. **`install.yml` is per-pathogen** — same skeleton, but the `--only` list of descriptors varies. The template `scripts/02_init_pathogen.py` derives it from which featurizers each pathogen's sub-models actually use (subset of `chemeleon,clamp,cddd`). A typical install.yml looks like:
   ```yaml
   python: "3.12"
   commands:
       - ["pip", "ersilia-pack-utils", "0.1.5"]
       - ["pip", "lazyqsar", "3.3.0"]
       - "lazyqsar setup --descriptors --only chemeleon,clamp"
   ```
   - **`ersilia-pack-utils`** — Ersilia Hub I/O conventions. `main.py` reads input via `read_smiles(input_file)` and writes output via `write_out(results, header, output_file)`, which dispatch on `.csv` / `.bin` extensions. No pandas roundtrip; pass the SMILES list straight into `lqsar_predict(smiles=…)`.
   - **`lazyqsar==3.3.0`** (NOT `lazyqsar[descriptors]`!) — base install only. The `[descriptors]` extra would resolve `torch>=2.6.0` against PyPI and pull the CUDA wheel (~3 GB) plus a dozen `nvidia-*` transitive deps that pip won't auto-remove later. Base install ships just numpy / onnxruntime / pandas / h5py / psutil / rich / loguru — no torch yet.
   - **`lazyqsar setup --descriptors --only …`** — `install_torch()` then runs `pip install torch --index-url https://download.pytorch.org/whl/cpu`. Because no torch is installed yet, this lands the CPU wheel fresh — no CUDA libs ever enter the env. Setup also pip-installs chemprop / rdkit / FPSim2 (chemprop transitively brings what chemeleon's descriptor needs at runtime — the `chemeleon` Python package itself is NOT required, see [lazy-qsar's chemeleon.py](https://github.com/ersilia-os/lazy-qsar/blob/main/lazyqsar/descriptors/chemeleon.py) for the chemprop-only fallback). `--only` restricts the descriptor-weight download to this pathogen's actual featurizers (~34 MB chemeleon + ~167 MB clamp for abaumannii; cddd adds ~415 MB when needed). Weights land in `$HOME/.lazyqsar/`. `03_test_pathogen.py` re-runs the same setup locally if files are missing.

4. **`predict_type="rank"` always.** Despite the name, lazyqsar's "rank" output is a calibrated, batch-independent probability-like score (not a relative ranking). The training repo's `scripts/12` and `scripts/14` both consume it as a probability. In **user-facing docs** (run_columns descriptions, metadata Interpretation, README) call it a "probability" — never "rank" and never "relative to the input batch."

5. **Consensus = W1–W7 + W8 + tanh transform.** Mirror `$PATH_TO_CAMM/scripts/14_consensus_scoring.py` exactly:
   - W1–W7: model-level quality weights from `reports.csv`.
   - W8: per-compound weight from `decision_cutoff_rank` (0 at/below cutoff, linear 0→1 above). **Don't skip W8** — older drafts of this file said to; that was wrong.
   - Average all 8 weights with uniform weights, weight prob_ranks, then tanh-restore the IQR with `k(M) = 2·(1 + 1.156·(1 − exp(−M/6.47)))`.
   - Output **one** consensus column: `consensus_score` (tanh-transformed). The pre-transform raw value is computed as an intermediate but **not** emitted.

6. **Output Dimension = 1 + number of sub-models.** For abaumannii (5 sub-models) it's 6. Verify against `$PATH_TO_CAMM/output/results/09_models/{pathogen}/` for each new pathogen.

7. **`run_columns.csv` descriptions are factual only.** State training data + cutoff + n. Never include interpretation language ("higher = more likely active") or batch-relativity caveats. See the golden example in the runbook.

8. **`metadata.yml` rules.** Edit (don't overwrite) the template. Hard rules — confirmed by CI schema validator (the gitbook docs are not always accurate; trust the validator + the controlled-vocab files):
   - **`Status: In progress`** (lowercase p; the gitbook says "In Progress" but that's wrong — the validator checks against [`status.txt`](https://github.com/ersilia-os/ersilia/blob/master/ersilia/hub/content/metadata/status.txt), which contains `Test / In maintenance / In progress / Ready / Archived`).
   - **Title ≥ 70 chars** (single string), **Description ≥ 200 chars** (avoid "endpoint" / PubChem unless the pathogen actually uses PubChem), **Interpretation < 200 chars** on one line.
   - **`Source: Local`** — single string, NOT a comma-joined list. The template ships `Source: Local, Online` which **fails**. Note: `Deployment:` IS a YAML list and can hold both — only `Source:` is restricted.
   - Other single-value fields the template ships as comma-strings (`Source Type`, `Task`, `Subtask`, `Output Consistency`, `Publication Type`) must be trimmed to **one** value. `Output:` is a YAML list.
   - **`Publication:`** must be **present** AND a **valid URL**. The validator has a bug — `Publication: None` triggers EmptyField, and omitting the key entirely triggers a KeyError. If there's no peer-reviewed paper, use the Source Code repo URL as a placeholder (e.g. `Publication: https://github.com/ersilia-os/chembl-antimicrobial-models`). See [ersilia/publish/test/services/checks.py:_check_model_publication](https://github.com/ersilia-os/ersilia/blob/master/ersilia/publish/test/services/checks.py).
   - Auto-generated keys (DockerHub, S3, Docker Architecture, Image Size, Computational Performance, Release, Contribution Date, …) should NOT be present in our YAML — Ersilia adds them at publish time. They show as `NOT PRESENT` in CI but that's informational only.

9. **Controlled vocabularies.** Three metadata fields draw from closed lists in `ersilia-os/ersilia`:
   - [`Tag`](https://github.com/ersilia-os/ersilia/blob/master/ersilia/hub/content/metadata/tag.txt) — after the May-2026 vocab refresh, species-abbreviation tags (`A.baumannii`, `C.albicans`, …) are gone. Species signalling now lives in `Target Organism` only. Our Tag block is `[ESKAPE if applicable, Antimicrobial activity, ChEMBL]`.
   - [`Biomedical Area`](https://github.com/ersilia-os/ersilia/blob/master/ersilia/hub/content/metadata/biomedical_area.txt) — disease-specific entries (`Pneumonia`, `Diarrheal diseases`, `Tuberculosis`, `Malaria`, `Gonorrhea`, `Schistosomiasis`, `Candidiasis`, `Peptic ulcer disease`, …) were added. Per-pathogen value lives in [`data/00_registry.csv`](data/00_registry.csv) under the `biomedical_area` column (`;`-separated for multi-value). Policy: ESKAPE pathogens layer `Antimicrobial resistance` on top of the disease entry; non-ESKAPE list disease only.
   - [`Target Organism`](https://github.com/ersilia-os/ersilia/blob/master/ersilia/hub/content/metadata/target_organism.txt) — restricted to Linnaean species. All 15 of our pathogens' `full_name` registry values match exactly.

   If a pathogen / area / tag is missing, **append it to the source-of-truth file in `ersilia/` before committing** (open a PR if you can't push directly).

10. **`run_output.csv` is machine-generated.** Never hand-edit it; Ersilia's CI byte-compares against a fresh `bash run.sh` invocation.

11. **Repo layout for the coordinator.** This repo holds CLAUDE.md (you're reading it), docs/, scripts/, and per-pathogen forks cloned in-place as `eos*/` (gitignored). Each fork has its own git history pointing to `arnaucoma24/{eosXXXX}`. Don't commit anything inside an `eos*/` dir from the coordinator's git — work in the fork's git instead.

---

## Pull-request checklist (step iv)

Before pushing the fork's PR, confirm:

- `model/checkpoints/models/` is populated with the sub-models (plain git — no LFS, no eosvc; size varies per pathogen, ~50–350 MB).
- `model/checkpoints/reports.csv` is the pathogen-filtered subset.
- `model/checkpoints/` does NOT contain a `featurizer_weights_home/` dir (descriptor weights live in `$HOME/.lazyqsar/`, downloaded at install time).
- `run_output.csv` is byte-identical to a fresh re-run.
- Title/Description/Interpretation respect the length rules from §8.
- All Tag/Biomedical Area/Target Organism entries are in the controlled vocab files.

Then:

```bash
cd eosXXXX
git add .gitignore install.yml metadata.yml \
        model/framework/code/main.py \
        model/framework/code/consensus.py \
        model/framework/columns/run_columns.csv \
        model/framework/examples/run_input.csv \
        model/framework/examples/run_output.csv \
        model/framework/fit/.gitkeep \
        model/checkpoints/             # ~50–350 MB; regular git
git commit -m "Add antimicrobial activity model for {Full pathogen name}"
git push origin main

gh pr create --repo ersilia-os/eosXXXX \
  --title "Add antimicrobial activity model for {Full pathogen name}" \
  --body "$(cat <<'EOF'
Related to ersilia-os/ersilia#<issue-number>.

Packages the {Full pathogen name} QSAR sub-models from ersilia-os/chembl-antimicrobial-models into a single Hub model.

- Output: 1 + N columns (\`consensus_score\` + per-sub-model probabilities).
- Consensus: W1-W7 + W8 quality-weighted average + tanh IQR-restoring transform, mirroring \`chembl-antimicrobial-models/scripts/14_consensus_scoring.py\`.
- Sub-model checkpoints ship in regular git; descriptor weights are downloaded at install time by \`lazyqsar setup\`.
- Tested locally on Python 3.12 with \`lazyqsar==3.3.0\` + \`lazyqsar setup --descriptors --only …\` (no \`[descriptors]\` extra, to avoid CUDA torch).

Per-pathogen procedure documented at https://github.com/ersilia-os/chembl-antimicrobial-hub-incorporation/blob/main/docs/per-pathogen-runbook.md.
EOF
)"
```

(Same body that `scripts/04_publish_pathogen.py:PR_BODY_TEMPLATE` emits — keep in sync if either changes.)

Once merged + workflows green, delete the personal fork (`gh repo delete arnaucoma24/eosXXXX --yes`) and update the [monitoring table](#monitoring-table).
