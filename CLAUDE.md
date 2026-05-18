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

1. **Checkpoints are tracked twice: eosvc AND Git LFS.** Two independent paths because they serve different consumers:
   - **eosvc** — every fork ships `access.json` with `{"checkpoints":"public","fit":"public"}`. Push files with `eosvc upload --path checkpoints/`; the Hub pulls them with `eosvc download --path checkpoints/` at install time.
   - **Git LFS** — `.gitattributes` LFS-tracks `*.onnx`, `*.pt`, `*.h5`, and the one big `cddd_encoder_smiles.csv`. The model-PR CI workflow (`actions/checkout` with `lfs: true`) needs these in the cloned tree because `ersilia -v test ... --from_dir` does not invoke eosvc.
   - The Ersilia template ships a stray `mock.txt` + matching LFS rule — delete those, then add the four real LFS rules. `.gitignore` should NOT exclude `model/checkpoints/` (LFS needs to see those files). `fit/` stays ignored.

2. **Two conda envs, never collapsed.**
   - `cam-hub-inc` (Python 3.10) — coordinator work: eosvc CLI, filtering `reports.csv`, `gh`, helper scripts.
   - `cam-models-runtime` (Python **3.12**) — shared model runtime, built from the `install.yml` template once and reused across every pathogen. Python 3.12 (not 3.10) because `chemprop==2.2.3` requires ≥3.11.

3. **`install.yml` is the same for every pathogen** — only the filename's eosXXXX changes:
   ```yaml
   python: "3.12"
   commands:
       - ["pip", "lazyqsar[all]", "3.2.1"]
       - ["pip", "ersilia-pack-utils", "0.1.5"]
       - ["pip", "eosvc", "1.1.0"]
   ```
   Use `lazyqsar[all]`, **not `[descriptors]`** — `classifier_predict`'s import chain hard-imports `xgboost`/`sklearn`/`joblib` at module load (all in the `[fit]` extra). Realistic env-size savings from dropping `[fit]` are < 1% on a 7 GB env, and dropping it requires either refactoring `main.py` to per-sub-model loading (5× slower inference) or waiting for the upstream lazy-import fix in [lazy-qsar#31](https://github.com/ersilia-os/lazy-qsar/issues/31). Don't hand-pin `numpy`/`pandas`/`onnxruntime`; let lazyqsar's pyproject pin them.

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

- `model/checkpoints/` contains the real ~600 MB tracked via Git LFS (`.gitattributes` has the four LFS rules).
- `access.json` + `.eosvc/access.lock.json` are committed.
- `.gitattributes` LFS-tracks `*.onnx`, `*.pt`, `*.h5`, and the one big `cddd_encoder_smiles.csv`.
- `run_output.csv` is byte-identical to a fresh re-run.
- Title/Description/Interpretation respect the length rules from §8.
- All Tag/Biomedical Area/Target Organism entries are in the controlled vocab files.

Then:

```bash
cd eosXXXX
git lfs install                       # one-time per machine
git add access.json .eosvc/access.lock.json .gitignore .gitattributes \
        install.yml metadata.yml \
        model/framework/code/main.py \
        model/framework/columns/run_columns.csv \
        model/framework/examples/run_input.csv \
        model/framework/examples/run_output.csv \
        model/checkpoints/             # ~600 MB; LFS-tracked via .gitattributes
git commit -m "Add antimicrobial activity model for {Full pathogen name}"
git push origin main

gh pr create --repo ersilia-os/eosXXXX \
  --title "Add antimicrobial activity model for {Full pathogen name}" \
  --body "Related to ersilia-os/ersilia#<issue-number>."
```

Once merged + workflows green, delete the personal fork (`gh repo delete arnaucoma24/eosXXXX --yes`) and update the [monitoring table](#monitoring-table).
