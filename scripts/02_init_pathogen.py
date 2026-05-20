#!/usr/bin/env python3
"""Scaffold an eosXXXX fork for one pathogen — the mechanical 90%.

What this script does (idempotent where it can be):
  1. Look up the pathogen's eosXXXX from the registry, or detect it from
     the issue's bot comment if not yet recorded.
  2. Fork ersilia-os/{eosXXXX} -> arnaucoma24/{eosXXXX} and clone into
     ./{eosXXXX}/ at the coordinator-repo root.
  3. Delete the template's mock.txt; rewrite .gitignore (model/checkpoints/
     ships via regular git; model/framework/fit/ and the descriptor
     weights dir stay ignored); touch model/framework/fit/.gitkeep.
  4. Copy the pathogen's sub-models from $PATH_TO_CAMM into
     model/checkpoints/models/<sub_model>/ and write the
     pathogen-filtered reports.csv at model/checkpoints/reports.csv.
  5. Pick 3 SMILES from the training positives (30-80 chars) and write
     model/framework/examples/run_input.csv.
  6. Write install.yml with a per-pathogen `--only` list (subset of
     chemeleon/clamp/cddd derived from the sub-models that will be copied).
  7. Generate DRAFT versions of main.py, run_columns.csv, and
     metadata.yml. These three files need Claude+human review before
     running 03_test_pathogen.py.

Usage:
    conda activate cam-hub-inc
    python scripts/02_init_pathogen.py --pathogen efaecium
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY  = os.path.join(REPO_ROOT, "data", "00_registry.csv")
PATH_TO_CAMM = os.environ.get(
    "PATH_TO_CAMM",
    "/aloy/home/acomajuncosa/Ersilia/chembl-antimicrobial-models",
)

# ---- Constants identical for every pathogen ----

# Descriptors lazyqsar can pre-download. morgan + rdkit don't need a download
# (rdkit computes them on the fly), so they're omitted.
_DOWNLOADABLE_DESCRIPTORS = ("chemeleon", "clamp", "cddd")


def _descriptors_needed(pathogen, model_names):
    """Scan `$PATH_TO_CAMM/output/results/09_models/{pathogen}/{sub_model}/`
    for the kept sub-models and return the subset of {chemeleon, clamp, cddd}
    that any of them use. Drives the --only list passed to
    `lazyqsar setup --descriptors`. Must be called after
    `_populate_checkpoints` so that filtered-out sub-models don't pull in
    descriptor weights that are never used.
    """
    src = os.path.join(PATH_TO_CAMM, "output", "results", "09_models", pathogen)
    needed = set()
    for sub in model_names:
        sub_path = os.path.join(src, sub)
        if not os.path.isdir(sub_path):
            continue
        for d in os.listdir(sub_path):
            if d in _DOWNLOADABLE_DESCRIPTORS:
                needed.add(d)
    # Preserve canonical ordering from _DOWNLOADABLE_DESCRIPTORS.
    return [d for d in _DOWNLOADABLE_DESCRIPTORS if d in needed]


# Sort hierarchy for sub-models in reports.csv / MODEL_NAMES. See
# docs/per-pathogen-runbook.md and the plan at
# ~/.claude/plans/zazzy-splashing-music.md for the rationale.
# Label semantics match CAMM's _W1_MAP in scripts/10_aggregate_reports.py:
# A and B are both "individual" datasets; M is merged; G is general.
_SOURCE_RANK = {"chembl": 0, "pubchem": 1}
_LABEL_RANK  = {"A": 0, "B": 1, "M": 2, "G": 3}
_AUROC_FLOOR = 0.7  # strict >; below this, CAMM's w3 already collapses to 0


def _sort_and_filter(reports_df):
    """Drop sub-models with auroc_mean <= 0.7, then sort by
    (source, label, n_compounds desc). Joins on `name` against
    07_datasets_metadata.csv to pull source+label.
    """
    import pandas as pd
    meta_path = os.path.join(PATH_TO_CAMM, "output", "results", "07_datasets_metadata.csv")
    meta = pd.read_csv(meta_path)[["pathogen", "name", "source", "label"]]
    df = reports_df.merge(meta, on=["pathogen", "name"], how="left", validate="one_to_one")
    missing = df[df["source"].isna() | df["label"].isna()]
    if not missing.empty:
        sys.exit(
            f"Sub-models missing in 07_datasets_metadata.csv: "
            f"{missing['model_name'].tolist()}"
        )
    df = df[df["auroc_mean"] > _AUROC_FLOOR].copy()
    df["_src"] = df["source"].map(_SOURCE_RANK)
    df["_lbl"] = df["label"].map(_LABEL_RANK)
    if df["_src"].isna().any() or df["_lbl"].isna().any():
        bad = df[df["_src"].isna() | df["_lbl"].isna()]
        sys.exit(
            f"Unrecognized source/label values: "
            f"{bad[['model_name', 'source', 'label']].to_dict('records')}"
        )
    df = df.sort_values(
        ["_src", "_lbl", "n_compounds"],
        ascending=[True, True, False],
    )
    return df.drop(columns=["_src", "_lbl", "source", "label"])


def _install_yml(descriptors_needed):
    only = ",".join(descriptors_needed)
    return f"""python: "3.12"
commands:
    - ["pip", "ersilia-pack-utils", "0.1.5"]
    - ["pip", "lazyqsar", "3.3.0"]
    - "lazyqsar setup --descriptors --only {only}"
"""

GITIGNORE_HEADER = """\
# Sub-models under model/checkpoints/models/ and model/checkpoints/reports.csv
# ship via regular git. Descriptor weights live in $HOME/.lazyqsar/ — they are
# downloaded at install time by `lazyqsar setup` and never committed here.
model/framework/fit/*
!model/framework/fit/.gitkeep
"""

MAIN_PY = '''\
import csv
import os
import sys

from ersilia_pack_utils.core import read_smiles, write_out
from lazyqsar.api.classifier_predict import predict

import consensus

input_file  = sys.argv[1]
output_file = sys.argv[2]
root        = os.path.dirname(os.path.abspath(__file__))
checkpoints = os.path.abspath(os.path.join(root, "..", "..", "checkpoints"))

# Sub-model order: every row of run_columns.csv except the leading consensus_score.
columns_file = os.path.abspath(os.path.join(root, "..", "columns", "run_columns.csv"))
with open(columns_file) as f:
    MODEL_NAMES = [row["name"] for row in csv.DictReader(f) if row["name"] != "consensus_score"]
model_dir_dict = {m: os.path.join(checkpoints, "models", m) for m in MODEL_NAMES}

_, smiles_list = read_smiles(input_file)
R, cols_ordered = predict(model_dir_dict, smiles=smiles_list, predict_type="rank")
results, header = consensus.compute_consensus(R, cols_ordered, MODEL_NAMES, checkpoints)
write_out(results, header, output_file)
'''


CONSENSUS_PY = '''\
"""Quality-weighted consensus across LazyQSAR sub-models.

Mirrors chembl-antimicrobial-models/scripts/14_consensus_scoring.py:
- W1..W7 are per-sub-model quality weights from reports.csv.
- W8 is a per-compound weight that ramps 0->1 above each sub-model's
  decision_cutoff_rank.
- All 8 weights are uniformly averaged into an effective per-compound,
  per-sub-model weight; the consensus is the weighted mean of prob_ranks;
  a tanh transform then restores the IQR that averaging compresses
  toward 0.5.
"""

import os
import numpy as np
import pandas as pd

_W_COLS = ["w1", "w2", "w3", "w4", "w5", "w6", "w7"]
_TANH_A, _TANH_TAU = 1.156, 6.47


def compute_consensus(R, cols_ordered, model_names, checkpoints_dir):
    """Build the model's output matrix.

    Args:
        R:               (n, K) prob_rank matrix returned by lqsar_predict.
        cols_ordered:    list of K column names matching R's columns (also from lqsar_predict).
        model_names:     canonical sub-model order for this pathogen (length M, M <= K).
        checkpoints_dir: path to model/checkpoints/ (must contain reports.csv).

    Returns:
        results: (n, 1+M) float array, rounded to 4 decimals.
                 results[:, 0] is the tanh-transformed consensus score.
                 results[:, 1:] is the per-sub-model prob_rank reordered to match model_names.
        header:  ["consensus_score", *model_names].
    """
    name_to_idx = {c: i for i, c in enumerate(cols_ordered)}
    prob_ranks = np.nan_to_num(
        R[:, [name_to_idx[m] for m in model_names]], nan=0.0
    )

    reports = pd.read_csv(os.path.join(checkpoints_dir, "reports.csv")).set_index("model_name")
    w_quality = np.array([reports.loc[m, _W_COLS].values for m in model_names], dtype=float)
    cutoffs   = np.array([reports.loc[m, "decision_cutoff_rank"] for m in model_names], dtype=float)

    c  = np.clip(cutoffs[np.newaxis, :], 0.0, 1.0 - 1e-9)
    w8 = np.where(prob_ranks <= c, 0.0, (prob_ranks - c) / (1.0 - c))

    n, M = prob_ranks.shape
    n_w  = len(_W_COLS) + 1
    w_all = np.empty((n, M, n_w))
    w_all[:, :, :len(_W_COLS)] = w_quality
    w_all[:, :,  len(_W_COLS)] = w8
    w_eff = np.average(w_all, axis=-1, weights=np.ones(n_w))

    raw = (prob_ranks * w_eff).sum(axis=1) / w_eff.sum(axis=1)
    k   = 2.0 * (1.0 + _TANH_A * (1.0 - np.exp(-M / _TANH_TAU)))
    consensus = 0.5 + 0.5 * np.tanh(k * (raw - 0.5)) / np.tanh(k / 2)

    results = np.round(np.column_stack([consensus, prob_ranks]), 4)
    header  = ["consensus_score", *model_names]
    return results, header
'''


# ---- Helpers ----

def _read_registry():
    with open(REGISTRY) as f:
        return list(csv.DictReader(f))


def _write_registry(rows):
    with open(REGISTRY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _detect_eosXXXX(issue_number):
    """Read issue comments, look for the bot's [ersilia-os/eosXXXX] link."""
    res = subprocess.run(
        ["gh", "api", f"repos/ersilia-os/ersilia/issues/{issue_number}/comments"],
        capture_output=True, text=True, check=True,
    )
    comments = json.loads(res.stdout)
    for c in comments:
        m = re.search(r"\[ersilia-os/(eos[a-z0-9]+)\]", c.get("body", ""))
        if m:
            return m.group(1)
    return None


def _fork_and_clone(eosXXXX, dest):
    """gh repo fork + git clone, both idempotent.

    `gh repo fork --org` only works for organisation accounts; arnaucoma24 is
    a user account, so we omit --org and let gh fork into the authenticated
    user's default account (which must be arnaucoma24).
    """
    subprocess.run(
        ["gh", "repo", "fork", f"ersilia-os/{eosXXXX}", "--clone=false"],
        check=False,  # "already exists" is fine
    )
    if not os.path.isdir(dest):
        subprocess.run(
            ["git", "clone", f"git@github.com:arnaucoma24/{eosXXXX}.git", dest],
            check=True,
        )


def _populate_checkpoints(pathogen, fork):
    """Copy sub-models + filtered reports.csv. Return sub-model order from reports.csv.

    Descriptor weights are NOT copied here. `lazyqsar setup --descriptors --cpu-torch
    --only …` (in install.yml) downloads them into $HOME/.lazyqsar/ at install time.
    """
    import pandas as pd
    ckpt = os.path.join(fork, "model", "checkpoints")
    os.makedirs(os.path.join(ckpt, "models"), exist_ok=True)

    src_models = os.path.join(PATH_TO_CAMM, "output", "results", "09_models", pathogen)
    if not os.path.isdir(src_models):
        sys.exit(f"No CAMM models dir for pathogen '{pathogen}': {src_models}")

    # reports.csv → pathogen subset, filtered (auroc_mean > 0.7) and
    # sorted by (source, label, n_compounds desc).
    reports_all = pd.read_csv(os.path.join(PATH_TO_CAMM, "output", "results", "10_reports.csv"))
    sub = reports_all[reports_all["pathogen"] == pathogen].copy()
    sub = sub.drop(columns=["predict_rank_actives", "predict_rank_inactives"], errors="ignore")
    sub = _sort_and_filter(sub)
    if sub.empty:
        sys.exit(
            f"All sub-models for {pathogen} fall below the AUROC>{_AUROC_FLOOR} cutoff."
        )
    sub.to_csv(os.path.join(ckpt, "reports.csv"), index=False)
    kept = set(sub["model_name"])

    # Sub-models: copy only the ones kept by the filter+sort step.
    for m in sorted(os.listdir(src_models)):
        if m not in kept:
            continue
        src = os.path.join(src_models, m)
        dst = os.path.join(ckpt, "models", m)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)

    return sub["model_name"].tolist()


def _pick_smiles(pathogen, fork, n=3):
    import pandas as pd
    pos_csv = os.path.join(PATH_TO_CAMM, "output", "results", "03_selected_positives.csv")
    df = pd.read_csv(pos_csv)
    hits = df[df["found_in"].str.contains(pathogen, na=False)]
    hits = hits[hits["smiles"].str.len().between(30, 80)]
    hits = hits.head(n)
    if len(hits) < n:
        sys.exit(f"Not enough positives for {pathogen}: only {len(hits)} found.")
    out = os.path.join(fork, "model", "framework", "examples", "run_input.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("smiles\n")
        for s in hits["smiles"]:
            f.write(s + "\n")


def _draft_main_py(fork):
    path = os.path.join(fork, "model", "framework", "code", "main.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(MAIN_PY)


def _draft_consensus_py(fork):
    path = os.path.join(fork, "model", "framework", "code", "consensus.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(CONSENSUS_PY)


def _consensus_threshold(cutoffs, w_quality):
    """Apply main.py's consensus formula to the per-sub-model decision_cutoff_rank
    values, treating them as the prob_ranks of a hypothetical compound that sits
    exactly on each sub-model's boundary. W8 = 0 at the boundary.

    Mirrors the math in MAIN_PY's consensus block. Returns the post-tanh value.
    """
    import numpy as np
    cutoffs   = np.asarray(cutoffs,   dtype=float)
    w_quality = np.asarray(w_quality, dtype=float)
    M = len(cutoffs)
    prob_ranks = cutoffs.reshape(1, -1)
    c  = np.clip(cutoffs[None, :], 0.0, 1.0 - 1e-9)
    w8 = np.where(prob_ranks <= c, 0.0, (prob_ranks - c) / (1.0 - c))
    n_w = w_quality.shape[1] + 1  # w1..w7 + w8 = 8
    w_all = np.empty((1, M, n_w))
    w_all[:, :, :w_quality.shape[1]] = w_quality
    w_all[:, :,  w_quality.shape[1]] = w8
    w_eff = np.average(w_all, axis=-1, weights=np.ones(n_w))
    raw = (prob_ranks * w_eff).sum(axis=1) / w_eff.sum(axis=1)
    A, T = 1.156, 6.47
    k = 2.0 * (1.0 + A * (1.0 - np.exp(-M / T)))
    return float(0.5 + 0.5 * np.tanh(k * (raw - 0.5)) / np.tanh(k / 2))


def _draft_run_columns(fork, model_names):
    """One row per sub-model with a placeholder description; Claude rewrites
    the assay-description part per memory feedback_run_columns_style. The
    `Recommended threshold: X.XXX.` suffix is auto-filled here and should be
    kept by Claude as-is.
    """
    import pandas as pd
    path = os.path.join(fork, "model", "framework", "columns", "run_columns.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    reports = pd.read_csv(os.path.join(fork, "model", "checkpoints", "reports.csv")).set_index("model_name")
    W_COLS  = ["w1", "w2", "w3", "w4", "w5", "w6", "w7"]
    cutoffs   = [float(reports.loc[m, "decision_cutoff_rank"]) for m in model_names]
    w_quality = [reports.loc[m, W_COLS].values for m in model_names]
    cons_thresh = _consensus_threshold(cutoffs, w_quality)

    with open(path, "w") as f:
        f.write("name,type,direction,description\n")
        f.write(
            f"consensus_score,float,high,Tanh-transformed quality-weighted consensus "
            f"probability across the {len(model_names)} sub-models. "
            f"Recommended threshold: {cons_thresh:.3f}.\n"
        )
        for m, ct in zip(model_names, cutoffs):
            # NEEDS CLAUDE REVIEW: rewrite the leading sentence per memory
            # `feedback_run_columns_style` ("Probability from sub-model trained on
            # ... (cutoff X; n=Y)"). Keep the trailing `Recommended threshold` sentence.
            # CRITICAL: no commas inside the description text — the field is
            # unquoted in the CSV; a comma breaks pandas parsing. Use ';' or
            # rephrase if a comma feels natural.
            f.write(
                f"{m},float,high,DRAFT — Probability from sub-model {m}. "
                f"Rewrite per 07_datasets_metadata.csv. "
                f"Recommended threshold: {ct:.3f}.\n"
            )


def _draft_metadata(fork, row, eosXXXX, model_names):
    tags = []
    if row["eskape"].strip().lower() == "true":
        tags.append("ESKAPE")
    tags.extend(["Antimicrobial activity", "ChEMBL"])
    tag_block = "\n".join(f"  - {t}" for t in tags)

    areas = [a.strip() for a in row["biomedical_area"].split(";") if a.strip()]
    if not areas:
        sys.exit(f"Empty biomedical_area for {row['pathogen']} in 00_registry.csv")
    area_block = "\n".join(f"  - {a}" for a in areas)

    metadata = f"""\
Identifier: {eosXXXX}
Slug: {row["slug"]}
Status: In progress
Title: {row["title"]}
Description: >
  {row["description"]}
Deployment:
  - Local
  - Online
Source: Local
Source Type: Internal
Task: Annotation
Subtask: Activity prediction
Input:
  - Compound
Input Dimension: 1
Output:
  - Score
Output Dimension: {1 + len(model_names)}
Output Consistency: Fixed
Interpretation: Probability of antimicrobial activity against {row["full_name"]} from {len(model_names)} ChEMBL-trained sub-models, plus a quality-weighted consensus score.
Tag:
{tag_block}
Biomedical Area:
{area_block}
Target Organism:
  - {row["full_name"]}
Publication Type: Other
Publication Year: 2026
Publication: https://github.com/ersilia-os/chembl-antimicrobial-models
Source Code: https://github.com/ersilia-os/chembl-antimicrobial-models
License: GPL-3.0-or-later
Contributor: arnaucoma24
"""
    with open(os.path.join(fork, "metadata.yml"), "w") as f:
        f.write(metadata)


# ---- Main ----

def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pathogen", required=True)
    args = p.parse_args()
    pathogen = args.pathogen

    rows = _read_registry()
    row  = next((r for r in rows if r["pathogen"] == pathogen), None)
    if row is None:
        sys.exit(f"Unknown pathogen '{pathogen}'.")
    if not row["issue_number"].strip():
        sys.exit(f"Open the issue first: python scripts/01_open_issue.py --pathogen {pathogen}")

    eosXXXX = row["eosXXXX"].strip()
    if not eosXXXX:
        print(f"Looking up eosXXXX from issue #{row['issue_number']}...")
        eosXXXX = _detect_eosXXXX(row["issue_number"])
        if not eosXXXX:
            sys.exit("Issue not yet approved (no bot comment with the eosXXXX link found). Try again after /approve.")
        row["eosXXXX"] = eosXXXX
        _write_registry(rows)
        print(f"  Detected eosXXXX={eosXXXX}; written back to registry.")

    fork = os.path.join(REPO_ROOT, eosXXXX)

    print(f"[1/7] Fork + clone ersilia-os/{eosXXXX} -> {fork}")
    _fork_and_clone(eosXXXX, fork)

    print(f"[2/7] Clean template + write constants")
    # mock.txt — delete if present (template leftover)
    mock = os.path.join(fork, "mock.txt")
    if os.path.exists(mock):
        subprocess.run(["git", "-C", fork, "rm", "-f", "mock.txt"], check=False)
    # .gitignore — prepend our block (preserve any existing content below)
    gi_path = os.path.join(fork, ".gitignore")
    existing = ""
    if os.path.exists(gi_path):
        with open(gi_path) as f:
            existing = f.read()
    # Strip any previous version of our block (covers both the eosvc/LFS-era
    # banner and the current regular-git banner), then prepend the fresh one.
    existing = re.sub(
        r"^# (?:model/checkpoints/ is intentionally|Sub-models under model/checkpoints/).*?(?=\n[^#!\nm]|\Z)",
        "", existing, count=1, flags=re.DOTALL,
    )
    with open(gi_path, "w") as f:
        f.write(GITIGNORE_HEADER + "\n" + existing.lstrip())
    # fit/.gitkeep
    fit_keep = os.path.join(fork, "model", "framework", "fit", ".gitkeep")
    os.makedirs(os.path.dirname(fit_keep), exist_ok=True)
    open(fit_keep, "a").close()

    print(f"[3/7] Populate model/checkpoints/")
    model_names = _populate_checkpoints(pathogen, fork)
    print(f"      Sub-models (in reports.csv order): {model_names}")

    # install.yml — `--only` list is per-pathogen, derived from the *kept*
    # sub-models' featurizers (must run after _populate_checkpoints).
    descriptors_needed = _descriptors_needed(pathogen, model_names)
    print(f"      Descriptors needed for {pathogen}: {descriptors_needed}")
    with open(os.path.join(fork, "install.yml"), "w") as f:
        f.write(_install_yml(descriptors_needed))

    print(f"[4/7] Pick 3 SMILES from training positives -> run_input.csv")
    _pick_smiles(pathogen, fork, n=3)

    print(f"[5/7] Draft main.py + consensus.py")
    _draft_main_py(fork)
    _draft_consensus_py(fork)

    print(f"[6/7] Draft run_columns.csv (DRAFT — Claude must rewrite descriptions)")
    _draft_run_columns(fork, model_names)

    print(f"[7/7] Draft metadata.yml")
    _draft_metadata(fork, row, eosXXXX, model_names)

    print()
    print("=" * 72)
    print(f"Files that need Claude + human review BEFORE running 03_test:")
    print(f"  {fork}/model/framework/columns/run_columns.csv")
    print(f"      ^ rewrite each sub-model row per the factual-only style memory")
    print(f"        (Probability from sub-model trained on … (cutoff X; n=Y)).")
    print(f"  {fork}/metadata.yml")
    print(f"      ^ verify Title >= 70 chars, Description >= 200 chars,")
    print(f"        Interpretation < 200 chars, Tag entries in controlled vocab.")
    print(f"main.py + consensus.py are family-templates — no per-pathogen edits needed.")
    print(f"Then:  python scripts/03_test_pathogen.py --pathogen {pathogen}")


if __name__ == "__main__":
    main()
