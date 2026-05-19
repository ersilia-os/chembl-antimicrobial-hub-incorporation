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
| abaumannii    | [#1849](https://github.com/ersilia-os/ersilia/issues/1849) | True  | True  | True  | True  | True  |
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

## Per-pathogen runbook

The full step-by-step procedure for steps iii–v lives in **[docs/per-pathogen-runbook.md](docs/per-pathogen-runbook.md)**. Read it (or skim the section you need) at the start of each pathogen. It was distilled from the abaumannii / eos21dr build session on 2026-05-16 and captures every gotcha we hit.

The reference filled model is at [eos21dr/](eos21dr/) — clone its layout and only edit the per-pathogen fields.

---

## Key principles (must-know in every session)

These override the older guidance that may still be sitting in old plans, notebooks, or PR descriptions.

1. **Checkpoints ship via regular git; descriptor weights downloaded at install time.** Two storage paths, each serving different consumers:
   - **Sub-models** (`model/checkpoints/models/{sub}/…`, ~50 MB per pathogen) and `model/checkpoints/reports.csv` → committed to the fork's regular git tree. No eosvc, no Git LFS — both were retired (see [chembl-antimicrobial-hub-incorporation@$THIS_COMMIT]) once descriptor weights moved to install-time download and the in-repo checkpoints fit comfortably in plain git. The Ersilia template ships a stray `mock.txt` — delete it.
   - **Descriptor weights** (`model/checkpoints/featurizer_weights_home/.lazyqsar/{chemeleon_mp.pt, clamp_encoder.onnx, cddd_encoder.onnx, …}`, ~200-615 MB per pathogen depending on which featurizers are used) → NOT in the repo. Gitignored except for `.gitkeep`. Downloaded at install time by `lazyqsar setup --descriptors --only <list> --target-dir model/checkpoints/featurizer_weights_home/.lazyqsar` (see Key Principle #3). On dev machines, `scripts/03_test_pathogen.py` runs the same setup command on demand if files are missing.
   - `.gitignore` should NOT exclude `model/checkpoints/models/` but MUST exclude `model/checkpoints/featurizer_weights_home/*` (with `.gitkeep` exception). `fit/` stays ignored.

2. **Two conda envs, never collapsed.**
   - `cam-hub-inc` (Python 3.10) — coordinator work: filtering `reports.csv`, `gh`, helper scripts.
   - `cam-models-runtime` (Python **3.12**) — shared model runtime, built from the `install.yml` template once and reused across every pathogen. Python 3.12 (not 3.10) because `chemprop==2.2.3` requires ≥3.11.

3. **`install.yml` is per-pathogen** — same skeleton, but the `--only` list of descriptors varies. The template `scripts/02_init_pathogen.py` derives it from which featurizers each pathogen's sub-models actually use (subset of `chemeleon,clamp,cddd`). abaumannii's `install.yml` looks like:
   ```yaml
   python: "3.12"
   commands:
       - ["pip", "torch", "2.6.0", "--index-url", "https://download.pytorch.org/whl/cpu"]
       - "pip install lazyqsar[descriptors]@git+https://github.com/ersilia-os/lazy-qsar.git@42ab866"
       - "lazyqsar setup --descriptors --only chemeleon,clamp --target-dir model/checkpoints/featurizer_weights_home/.lazyqsar"
       - ["pip", "ersilia-pack-utils", "0.1.5"]
   ```
   Note: the lazyqsar line is a **raw string command**, not a list. `ersilia-pack`'s YAML install parser (`_convert_pip_entry_to_bash`) treats the 3rd element of any `["pip", ...]` list as a version and rejects entries with fewer than 3 elements — PEP 508 direct references (`pkg @ git+url`) don't fit that schema. Raw strings bypass that check.
   Why each line, in order:
   - **CPU torch FIRST** so the subsequent `lazyqsar[descriptors]` install sees `torch>=2.6.0` already satisfied and won't pull the default PyPI CUDA wheel (~3 GB of NVIDIA libs we don't need).
   - **`lazyqsar[descriptors] @ git+…@42ab866`** — pinned to the post-3.2.1 commit that ships lazy imports of `xgboost`/`sklearn`/`joblib` (fixes [lazy-qsar#31](https://github.com/ersilia-os/lazy-qsar/issues/31)) plus the `--only` / `--target-dir` flags + `download_clamp()` (fixes [lazy-qsar#33](https://github.com/ersilia-os/lazy-qsar/issues/33)) plus the entry-point SMILES validation refactor. Switch to a tagged release once one cuts (likely `v3.2.2`).
   - **`lazyqsar setup --descriptors --only … --target-dir …`** materialises just the descriptor weights this pathogen uses (~34 MB chemeleon + ~167 MB clamp for abaumannii; cddd adds ~415 MB when needed) into the fork's checkpoint tree at install time. The descriptor weights are NOT bundled in the repo — gitignored. `02_init` writes the `--only` list per-pathogen by scanning sub-model dirs in CAMM; `03_test_pathogen.py` re-runs the same setup locally if files are missing (the shared cam-models-runtime env was built once and doesn't know about each new pathogen).
   - **`ersilia-pack-utils`** — Ersilia Hub I/O conventions.

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
   - [`Tag`](https://github.com/ersilia-os/ersilia/blob/main/ersilia/hub/content/metadata/tag.txt)
   - [`Biomedical Area`](https://github.com/ersilia-os/ersilia/blob/main/ersilia/hub/content/metadata/biomedical_area.txt) — note: there's no "Infectious disease"; use `Antimicrobial resistance`.
   - [`Target Organism`](https://github.com/ersilia-os/ersilia/blob/main/ersilia/hub/content/metadata/target_organism.txt) — all 15 of our pathogens are in there.

   If a pathogen / area / tag is missing, **append it to the source-of-truth file in `ersilia/` before committing** (open a PR if you can't push directly).

10. **`run_output.csv` is machine-generated.** Never hand-edit it; Ersilia's CI byte-compares against a fresh `bash run.sh` invocation.

11. **Repo layout for the coordinator.** This repo holds CLAUDE.md (you're reading it), docs/, scripts/, and per-pathogen forks cloned in-place as `eos*/` (gitignored). Each fork has its own git history pointing to `arnaucoma24/{eosXXXX}`. Don't commit anything inside an `eos*/` dir from the coordinator's git — work in the fork's git instead.

---

## Pull-request checklist (step iv)

Before pushing the fork's PR, confirm:

- `model/checkpoints/models/` is populated with the sub-models (~50 MB total, plain git — no LFS, no eosvc).
- `model/checkpoints/reports.csv` is the pathogen-filtered subset.
- `model/checkpoints/featurizer_weights_home/` contains only `.gitkeep` (descriptor weights are downloaded at install time).
- `run_output.csv` is byte-identical to a fresh re-run.
- Title/Description/Interpretation respect the length rules from §8.
- All Tag/Biomedical Area/Target Organism entries are in the controlled vocab files.

Then:

```bash
cd eosXXXX
git add .gitignore install.yml metadata.yml \
        model/framework/code/main.py \
        model/framework/columns/run_columns.csv \
        model/framework/examples/run_input.csv \
        model/framework/examples/run_output.csv \
        model/framework/fit/.gitkeep \
        model/checkpoints/             # ~50 MB; regular git
git commit -m "Add antimicrobial activity model for {Full pathogen name}"
git push origin main

gh pr create --repo ersilia-os/eosXXXX \
  --title "Add antimicrobial activity model for {Full pathogen name}" \
  --body "$(cat <<'EOF'
Related to ersilia-os/ersilia#<issue-number>.

Packages the {Full pathogen name} QSAR sub-models from ersilia-os/chembl-antimicrobial-models into a single Hub model.

- Output: 1 + N columns (\`consensus_score\` + per-sub-model probabilities).
- Consensus: W1-W7 + W8 quality-weighted average + tanh IQR-restoring transform, mirroring \`chembl-antimicrobial-models/scripts/14_consensus_scoring.py\`.
- Sub-model checkpoints (~50 MB) ship in regular git; descriptor weights are downloaded at install time by \`lazyqsar setup\`.
- Tested locally on Python 3.12 with \`lazyqsar[descriptors]@42ab866\`.

Per-pathogen procedure documented at https://github.com/ersilia-os/chembl-antimicrobial-hub-incorporation/blob/main/docs/per-pathogen-runbook.md.
EOF
)"
```

(Same body that `scripts/04_publish_pathogen.py:PR_BODY_TEMPLATE` emits — keep in sync if either changes.)

Once merged + workflows green, delete the personal fork (`gh repo delete arnaucoma24/eosXXXX --yes`) and update the [monitoring table](#monitoring-table).
