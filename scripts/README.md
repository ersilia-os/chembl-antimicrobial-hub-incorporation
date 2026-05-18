# scripts/

Helper scripts for incorporating one antimicrobial-activity QSAR model per pathogen. All `.py` scripts take a single `--pathogen <code>` flag (matching a row in [../data/00_registry.csv](../data/00_registry.csv)). See [../docs/per-pathogen-runbook.md](../docs/per-pathogen-runbook.md) for the manual procedure and the full context.

Run each script from the coordinator-repo root with the `cam-hub-inc` env active.

## Files

### ../data/00_registry.csv
Source of truth: 15 rows, one per pathogen. Pre-filled at session start with `pathogen`, `full_name`, `short_tag`, `eskape`, `data_sources`, `slug`, `title`, `description`. `issue_number` is filled by `01_open_issue.py`; `eosXXXX` is filled by `02_init_pathogen.py` after detecting the bot comment on the issue.

### 01_open_issue.py
Opens a Model Request issue at `ersilia-os/ersilia` with the registry's title + description and the standard Tag set (short_tag, optional ESKAPE, `Antimicrobial activity`, `ChEMBL`). Writes the new issue number back to the registry.

**Cutoff/rule:** Bails if the registry row already has an `issue_number` — re-running is a no-op.

### 02_init_pathogen.py
Mechanical scaffolding of the fork. Looks up `eosXXXX` from the issue's bot comment (or uses the value already in the registry); forks `ersilia-os/{eosXXXX}` to `arnaucoma24/{eosXXXX}` and clones it into `./{eosXXXX}/`; writes `.gitignore` (sub-models under `model/checkpoints/` ship via regular git; `featurizer_weights_home/` stays ignored — downloaded at install time) and a per-pathogen `install.yml`; copies sub-models + filtered `reports.csv` from `$PATH_TO_CAMM`; picks 3 SMILES from `03_selected_positives.csv` (30-80 chars). Generates **drafts** of `main.py` (with `MODEL_NAMES` derived from `reports.csv`), `run_columns.csv`, and `metadata.yml`. These three drafts need a Claude+human review before running 03.

### 03_test_pathogen.py
Activates `cam-models-runtime`, runs `bash model/framework/run.sh`, and asserts:
- Output file produced.
- Column names match `run_columns.csv` in order.
- All values in `[0, 1]`.
- Re-running produces a byte-identical file.

Exits non-zero on any failure.

### 04_publish_pathogen.py
`git add` the standard allowlist, commit, `git push origin main` (regular git — sub-models are ~50 MB total), `gh pr create` from `arnaucoma24/{eosXXXX}` to `ersilia-os/{eosXXXX}`. The PR body links the originating issue (`Related to …` — does NOT auto-close, per user preference).

## Standard per-pathogen workflow

```bash
conda activate cam-hub-inc

# 1. Open the model-request issue
python scripts/01_open_issue.py --pathogen efaecium
# (wait for someone to /approve the issue; bot auto-creates ersilia-os/eosXXXX)

# 2. Scaffold the fork
python scripts/02_init_pathogen.py --pathogen efaecium
# Now ask Claude to review the three drafted files:
#   ./eosXXXX/model/framework/code/main.py
#   ./eosXXXX/model/framework/columns/run_columns.csv
#   ./eosXXXX/metadata.yml

# 3. Run the model end-to-end + verify
python scripts/03_test_pathogen.py --pathogen efaecium

# 4. Publish
python scripts/04_publish_pathogen.py --pathogen efaecium
# Watch CI:  gh pr checks <PR-num> --repo ersilia-os/eosXXXX
# After CI green + PR merged: close the issue and delete the fork manually.
```

## Smoke test against abaumannii

To validate the scripts before running on a new pathogen, you can re-run `02_init_pathogen.py --pathogen abaumannii` from a clean state and diff the regenerated `./eos21dr/` against the merged version. The three "draft" files (main.py / run_columns.csv / metadata.yml) won't byte-match (Claude's review made changes), but everything else should.

## Pre-flight gotchas (from CLAUDE.md key principles)

- The `cam-models-runtime` env must already exist before running 03 (built once from any fork's `install.yml`).
- 6 pathogens have a `short_tag` that is not yet in `ersilia/hub/content/metadata/tag.txt`. Append them to that file (separate PR to ersilia-os/ersilia) before publishing those pathogens, or the schema check will fail on `Model Tag`. Affected: `C.albicans, Enterobacter, Campylobacter, H.pylori, S.mansoni, S.pneumoniae`.
- A GitHub auth token via `gh auth login` (HTTPS) is required for 01 (issue create) and 04 (PR create).
