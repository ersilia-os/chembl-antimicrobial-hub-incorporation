#!/usr/bin/env python3
"""git commit + git push + gh pr create.

Commits the per-pathogen fork and opens the PR from arnaucoma24/{eosXXXX}
into ersilia-os/{eosXXXX}. Everything (including model/checkpoints/) ships
via regular git — no eosvc, no Git LFS.

Usage:
    conda activate cam-hub-inc
    python scripts/04_publish_pathogen.py --pathogen efaecium
"""

import argparse
import csv
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY  = os.path.join(REPO_ROOT, "data", "00_registry.csv")

PR_TITLE_TEMPLATE = "Add antimicrobial activity model for {full_name}"
PR_BODY_TEMPLATE  = """\
Related to ersilia-os/ersilia#{issue_number}.

Packages the {full_name} QSAR sub-models from ersilia-os/chembl-antimicrobial-models into a single Hub model.

- Output: 1 + N columns (`consensus_score` + per-sub-model probabilities).
- Consensus: W1-W7 + W8 quality-weighted average + tanh IQR-restoring transform, mirroring `chembl-antimicrobial-models/scripts/14_consensus_scoring.py`.
- Sub-model checkpoints (~50 MB) ship in regular git; descriptor weights are downloaded at install time by `lazyqsar setup`.
- Tested locally on Python 3.12 with `lazyqsar[descriptors]@42ab866`.

Per-pathogen procedure documented at https://github.com/ersilia-os/chembl-antimicrobial-hub-incorporation/blob/main/docs/per-pathogen-runbook.md.
"""

# Files we add to git for the commit. model/checkpoints/ holds the
# sub-models (~50 MB total) and reports.csv — both ship in regular git.
FILES_TO_COMMIT = [
    ".gitignore",
    "install.yml",
    "metadata.yml",
    "model/framework/code/main.py",
    "model/framework/columns/run_columns.csv",
    "model/framework/examples/run_input.csv",
    "model/framework/examples/run_output.csv",
    "model/checkpoints/",
    "model/framework/fit/.gitkeep",
]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pathogen", required=True)
    args = p.parse_args()

    with open(REGISTRY) as f:
        rows = list(csv.DictReader(f))
    row = next((r for r in rows if r["pathogen"] == args.pathogen), None)
    if row is None or not row["eosXXXX"].strip():
        sys.exit(f"Run 02_init_pathogen.py --pathogen {args.pathogen} first.")

    eosXXXX = row["eosXXXX"]
    fork    = os.path.join(REPO_ROOT, eosXXXX)
    if not os.path.isdir(fork):
        sys.exit(f"Fork directory missing: {fork}")

    # 1. git add (everything under model/checkpoints/ is regular git)
    print(f"[1/3] git add")
    existing = [p for p in FILES_TO_COMMIT if os.path.exists(os.path.join(fork, p))]
    subprocess.run(["git", "add", *existing], cwd=fork, check=True)

    # 2. Commit. May report "nothing to commit" if previously committed; that's OK.
    commit_msg = f"Add antimicrobial activity model for {row['full_name']}"
    res = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=fork, capture_output=True, text=True,
    )
    if res.returncode != 0 and "nothing to commit" not in (res.stdout + res.stderr):
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        sys.exit("FAIL: git commit failed.")

    print(f"[2/3] git push origin main")
    res = subprocess.run(["git", "push", "origin", "main"], cwd=fork)
    if res.returncode != 0:
        sys.exit("FAIL: git push failed.")

    # 3. PR
    print(f"[3/3] gh pr create")
    title = PR_TITLE_TEMPLATE.format(full_name=row["full_name"])
    body  = PR_BODY_TEMPLATE.format(
        issue_number=row["issue_number"],
        full_name=row["full_name"],
        eosXXXX=eosXXXX,
    )
    res = subprocess.run(
        ["gh", "pr", "create",
         "--repo", f"ersilia-os/{eosXXXX}",
         "--head", "arnaucoma24:main",
         "--base", "main",
         "--title", title,
         "--body", body],
        cwd=fork, capture_output=True, text=True,
    )
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        # Likely "PR already exists" — print stderr but don't crash hard.
        sys.stderr.write(res.stderr)
        if "already exists" not in res.stderr:
            sys.exit("FAIL: gh pr create failed.")

    print()
    print("=" * 60)
    print(f"Done. Watch CI:  gh pr checks 1 --repo ersilia-os/{eosXXXX}")
    print(f"After CI is green and the PR merges, manually:")
    print(f"  - close ersilia-os/ersilia#{row['issue_number']}")
    print(f"  - delete the fork:  gh repo delete arnaucoma24/{eosXXXX} --yes")
    print(f"  - update the monitoring table in CLAUDE.md.")


if __name__ == "__main__":
    main()
