#!/usr/bin/env python3
"""Open a Model Request issue at ersilia-os/ersilia for one pathogen.

Reads scripts/00_registry.csv for the pathogen's metadata, composes the
issue body in the format the Ersilia template expects, calls `gh issue
create`, and writes the issue number back into the registry.

Usage:
    conda activate cam-hub-inc
    python scripts/01_open_issue.py --pathogen efaecium
"""

import argparse
import csv
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY  = os.path.join(REPO_ROOT, "scripts", "00_registry.csv")

# The Ersilia issue-template uses "### Section" markdown blocks; mirror that
# so the issue is recognised as a "new-model" request.
BODY_TEMPLATE = """\
### Model Name
{title}

### Model Description
{description}

### Slug
{slug}

### Tag
{tags}

### Publication
_No response_

### Source Code
https://github.com/ersilia-os/chembl-antimicrobial-models

### License
GPL-3.0-or-later
"""


def _build_tags(row):
    """Match the abaumannii pattern: short_tag (+ ESKAPE if applicable) + Antimicrobial activity + ChEMBL."""
    tags = [row["short_tag"]]
    if row["eskape"].strip().lower() == "true":
        tags.append("ESKAPE")
    tags.append("Antimicrobial activity")
    tags.append("ChEMBL")
    return ", ".join(tags)


def _read_registry():
    with open(REGISTRY) as f:
        rows = list(csv.DictReader(f))
    return rows


def _write_registry(rows):
    with open(REGISTRY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pathogen", required=True, help="pathogen short code (e.g. efaecium)")
    args = p.parse_args()

    rows = _read_registry()
    row  = next((r for r in rows if r["pathogen"] == args.pathogen), None)
    if row is None:
        sys.exit(f"Unknown pathogen '{args.pathogen}'. Add it to {REGISTRY} first.")
    if row["issue_number"].strip():
        sys.exit(f"Issue already opened for {args.pathogen}: #{row['issue_number']}")

    body = BODY_TEMPLATE.format(
        title=row["title"],
        description=row["description"],
        slug=row["slug"],
        tags=_build_tags(row),
    )

    print(f"Creating issue for {args.pathogen} at ersilia-os/ersilia...")
    res = subprocess.run(
        ["gh", "issue", "create", "--repo", "ersilia-os/ersilia",
         "--title", row["title"], "--body", body, "--label", "new-model"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        sys.exit(f"gh issue create failed:\n{res.stderr}")

    url = res.stdout.strip()
    issue_num = url.rstrip("/").rsplit("/", 1)[-1]

    row["issue_number"] = issue_num
    _write_registry(rows)

    print(f"  Issue #{issue_num} created: {url}")
    print("  Wait for /approve to be applied; an Ersilia bot will then auto-create")
    print(f"  ersilia-os/eosXXXX. Once that happens, run:")
    print(f"    python scripts/02_init_pathogen.py --pathogen {args.pathogen}")


if __name__ == "__main__":
    main()
