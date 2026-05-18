#!/usr/bin/env python3
"""Scaffold an eosXXXX fork for one pathogen — the mechanical 90%.

What this script does (idempotent where it can be):
  1. Look up the pathogen's eosXXXX from the registry, or detect it from
     the issue's bot comment if not yet recorded.
  2. Fork ersilia-os/{eosXXXX} -> arnaucoma24/{eosXXXX} and clone into
     ./{eosXXXX}/ at the coordinator-repo root.
  3. Delete the template's mock.txt; rewrite .gitattributes with our
     four real LFS rules; rewrite .gitignore so model/checkpoints is
     visible to git (LFS-tracked) but model/framework/fit/ stays ignored;
     touch model/framework/fit/.gitkeep.
  4. Copy the pathogen's sub-models from $PATH_TO_CAMM into
     model/checkpoints/models/<sub_model>/, copy featurizer weights into
     model/checkpoints/featurizer_weights_home/.lazyqsar/, and write the
     pathogen-filtered reports.csv at model/checkpoints/reports.csv.
  5. Pick 3 SMILES from the training positives (30-80 chars) and write
     model/framework/examples/run_input.csv.
  6. Write install.yml (constant for every pathogen).
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

INSTALL_YML = """python: "3.12"
commands:
    - ["pip", "lazyqsar[all]", "3.2.1"]
    - ["pip", "ersilia-pack-utils", "0.1.5"]
    - ["pip", "eosvc", "1.1.0"]
"""

GITATTRIBUTES = """\
*.onnx filter=lfs diff=lfs merge=lfs -text
*.pt filter=lfs diff=lfs merge=lfs -text
*.h5 filter=lfs diff=lfs merge=lfs -text
model/checkpoints/featurizer_weights_home/.lazyqsar/cddd_encoder_smiles.csv filter=lfs diff=lfs merge=lfs -text
"""

ACCESS_JSON = """\
{
  "checkpoints": "public",
  "fit": "public"
}
"""

GITIGNORE_HEADER = """\
# model/checkpoints/ is intentionally NOT ignored — tracked via Git LFS
# (see .gitattributes). eosvc still uploads the same files to S3 in
# parallel; the Hub uses eosvc at install time, CI uses LFS.
model/framework/fit/*
!model/framework/fit/.gitkeep
"""

MAIN_PY = '''\
import os
import sys

import numpy as np
import pandas as pd

root        = os.path.dirname(os.path.abspath(__file__))
checkpoints = os.path.abspath(os.path.join(root, "..", "..", "checkpoints"))
input_file  = sys.argv[1]
output_file = sys.argv[2]

# Isolate matplotlib's config/cache dir BEFORE lazyqsar import. Without
# this, matplotlib (transitively imported by lazyqsar's descriptor stack)
# writes its font cache to $HOME/.cache/matplotlib — and we set HOME below
# to point at our bundled featurizer weights, which would pollute
# model/checkpoints/featurizer_weights_home/.cache/ on every run.
# See https://github.com/ersilia-os/lazy-qsar/issues (TODO).
import atexit, shutil, tempfile
_mpl_dir = tempfile.mkdtemp(prefix="mpl_")
os.environ["MPLCONFIGDIR"] = _mpl_dir
atexit.register(lambda: shutil.rmtree(_mpl_dir, ignore_errors=True))

# LazyQSAR locates featurizer weights via $HOME/.lazyqsar/ — point it at our bundled copy.
os.environ["HOME"] = os.path.join(checkpoints, "featurizer_weights_home")

from lazyqsar.api.classifier_predict import predict as lqsar_predict

MODEL_NAMES = [
{model_names_block}
]
model_dir_dict = {{m: os.path.join(checkpoints, "models", m) for m in MODEL_NAMES}}

# One call: descriptors are shared across all sub-models.
tmp_out = output_file + ".tmp"
lqsar_predict(
    model_dir=model_dir_dict,
    input_csv=input_file,
    output_csv=tmp_out,
    predict_type="rank",
)
ranks_df = pd.read_csv(tmp_out)
os.remove(tmp_out)

# Consensus (mirrors chembl-antimicrobial-models/scripts/14_consensus_scoring.py).
reports = pd.read_csv(os.path.join(checkpoints, "reports.csv")).set_index("model_name")
W_COLS = ["w1", "w2", "w3", "w4", "w5", "w6", "w7"]
W_ALL_WEIGHTS = np.ones(len(W_COLS) + 1)

prob_ranks = ranks_df[MODEL_NAMES].fillna(0.0).values
w_quality  = np.array([reports.loc[m, W_COLS].values for m in MODEL_NAMES], dtype=float)
cutoffs    = np.array([reports.loc[m, "decision_cutoff_rank"] for m in MODEL_NAMES], dtype=float)

# w8: per-compound weight — 0 at/below decision cutoff, linear 0->1 above it.
c  = np.clip(cutoffs[np.newaxis, :], 0.0, 1.0 - 1e-9)
w8 = np.where(prob_ranks <= c, 0.0, (prob_ranks - c) / (1.0 - c))

n, M = prob_ranks.shape
w_all = np.empty((n, M, len(W_ALL_WEIGHTS)))
w_all[:, :, :len(W_COLS)] = w_quality
w_all[:, :,  len(W_COLS)] = w8
w_eff = np.average(w_all, axis=-1, weights=W_ALL_WEIGHTS)

consensus_raw = (prob_ranks * w_eff).sum(axis=1) / w_eff.sum(axis=1)

# Tanh IQR-restoring transform — k depends only on number of sub-models.
_TANH_A, _TANH_TAU = 1.156, 6.47
k = 2.0 * (1.0 + _TANH_A * (1.0 - np.exp(-M / _TANH_TAU)))
consensus = 0.5 + 0.5 * np.tanh(k * (consensus_raw - 0.5)) / np.tanh(k / 2)

out = pd.DataFrame({{
    "consensus_score": consensus.round(4),
    **{{m: ranks_df[m].round(4).values for m in MODEL_NAMES}},
}})
out.to_csv(output_file, index=False)
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
    """Copy sub-models + featurizer weights + filtered reports.csv. Return sub-model order from reports.csv."""
    import pandas as pd
    ckpt = os.path.join(fork, "model", "checkpoints")
    os.makedirs(os.path.join(ckpt, "models"), exist_ok=True)

    # Sub-models
    src_models = os.path.join(PATH_TO_CAMM, "output", "results", "09_models", pathogen)
    if not os.path.isdir(src_models):
        sys.exit(f"No CAMM models dir for pathogen '{pathogen}': {src_models}")
    for m in sorted(os.listdir(src_models)):
        src = os.path.join(src_models, m)
        dst = os.path.join(ckpt, "models", m)
        if os.path.isdir(src) and not os.path.exists(dst):
            shutil.copytree(src, dst)

    # Featurizer weights
    src_feat = os.path.join(PATH_TO_CAMM, "output", "results", "08_weights", ".lazyqsar")
    dst_feat = os.path.join(ckpt, "featurizer_weights_home", ".lazyqsar")
    os.makedirs(dst_feat, exist_ok=True)
    for f in os.listdir(src_feat):
        src = os.path.join(src_feat, f)
        dst = os.path.join(dst_feat, f)
        if not os.path.exists(dst):
            shutil.copy(src, dst)

    # reports.csv → pathogen subset, in 10_reports.csv order
    reports_all = pd.read_csv(os.path.join(PATH_TO_CAMM, "output", "results", "10_reports.csv"))
    sub = reports_all[reports_all["pathogen"] == pathogen].copy()
    sub.to_csv(os.path.join(ckpt, "reports.csv"), index=False)

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


def _draft_main_py(fork, model_names):
    block = "\n".join(f'    "{m}",' for m in model_names)
    path = os.path.join(fork, "model", "framework", "code", "main.py")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(MAIN_PY.format(model_names_block=block))


def _draft_run_columns(fork, model_names):
    """One row per sub-model with a placeholder description; Claude rewrites these per memory feedback_run_columns_style."""
    path = os.path.join(fork, "model", "framework", "columns", "run_columns.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("name,type,direction,description\n")
        f.write(f"consensus_score,float,high,Tanh-transformed quality-weighted consensus probability across the {len(model_names)} sub-models.\n")
        for m in model_names:
            # NEEDS CLAUDE REVIEW: rewrite per `feedback_run_columns_style` memory
            # ("Probability from sub-model trained on … (cutoff X; n=Y)").
            f.write(f"{m},float,high,DRAFT — Probability from sub-model {m}. Rewrite per 07_datasets_metadata.csv.\n")


def _draft_metadata(fork, row, eosXXXX, model_names):
    tags = [row["short_tag"]]
    if row["eskape"].strip().lower() == "true":
        tags.append("ESKAPE")
    tags.extend(["Antimicrobial activity", "ChEMBL"])
    tag_block = "\n".join(f"  - {t}" for t in tags)

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
  - Antimicrobial resistance
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
    # .gitattributes — write real LFS rules
    with open(os.path.join(fork, ".gitattributes"), "w") as f:
        f.write(GITATTRIBUTES)
    # access.json
    with open(os.path.join(fork, "access.json"), "w") as f:
        f.write(ACCESS_JSON)
    # .gitignore — prepend our block (preserve any existing content below)
    gi_path = os.path.join(fork, ".gitignore")
    existing = ""
    if os.path.exists(gi_path):
        with open(gi_path) as f:
            existing = f.read()
    # Strip any previous version of our block, then prepend the fresh one.
    existing = re.sub(
        r"^# model/checkpoints/ is intentionally.*?(?=\n[^#!\nm]|\Z)",
        "", existing, count=1, flags=re.DOTALL,
    )
    with open(gi_path, "w") as f:
        f.write(GITIGNORE_HEADER + "\n" + existing.lstrip())
    # fit/.gitkeep
    fit_keep = os.path.join(fork, "model", "framework", "fit", ".gitkeep")
    os.makedirs(os.path.dirname(fit_keep), exist_ok=True)
    open(fit_keep, "a").close()
    # install.yml
    with open(os.path.join(fork, "install.yml"), "w") as f:
        f.write(INSTALL_YML)

    print(f"[3/7] Populate model/checkpoints/")
    model_names = _populate_checkpoints(pathogen, fork)
    print(f"      Sub-models (in reports.csv order): {model_names}")

    print(f"[4/7] Pick 3 SMILES from training positives -> run_input.csv")
    _pick_smiles(pathogen, fork, n=3)

    print(f"[5/7] Draft main.py")
    _draft_main_py(fork, model_names)

    print(f"[6/7] Draft run_columns.csv (DRAFT — Claude must rewrite descriptions)")
    _draft_run_columns(fork, model_names)

    print(f"[7/7] Draft metadata.yml")
    _draft_metadata(fork, row, eosXXXX, model_names)

    print()
    print("=" * 72)
    print(f"Drafted 3 files that need Claude + human review BEFORE running 03_test:")
    print(f"  {fork}/model/framework/code/main.py")
    print(f"      ^ verify MODEL_NAMES order matches reports.csv.")
    print(f"  {fork}/model/framework/columns/run_columns.csv")
    print(f"      ^ rewrite each sub-model row per the factual-only style memory")
    print(f"        (Probability from sub-model trained on … (cutoff X; n=Y)).")
    print(f"  {fork}/metadata.yml")
    print(f"      ^ verify Title >= 70 chars, Description >= 200 chars,")
    print(f"        Interpretation < 200 chars, Tag entries in controlled vocab.")
    print(f"Then:  python scripts/03_test_pathogen.py --pathogen {pathogen}")


if __name__ == "__main__":
    main()
