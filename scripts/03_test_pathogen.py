#!/usr/bin/env python3
"""Run bash run.sh against the fork's examples and verify the output.

Activates the shared cam-models-runtime conda env, runs the model, and
checks:
  - Output file is produced.
  - Column names match run_columns.csv (in order).
  - All values are in [0, 1].
  - Re-running on the same input produces a byte-identical file.

Exits non-zero on any failure.

Usage:
    conda activate cam-hub-inc
    python scripts/03_test_pathogen.py --pathogen efaecium
"""

import argparse
import csv
import os
import subprocess
import sys

REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY    = os.path.join(REPO_ROOT, "data", "00_registry.csv")
CONDA_SH    = os.environ.get(
    "CONDA_SH",
    os.path.expanduser("~/programs/miniconda3/etc/profile.d/conda.sh"),
)
RUNTIME_ENV = "cam-models-runtime"

# Descriptors lazyqsar can pre-download. morgan + rdkit are computed on the fly.
_DOWNLOADABLE_DESCRIPTORS = ("chemeleon", "clamp", "cddd")


def _descriptors_needed(fork):
    """Scan `<fork>/model/checkpoints/models/{sub_model}/` and return the
    subset of {chemeleon, clamp, cddd} that appears in any sub-model dir."""
    src = os.path.join(fork, "model", "checkpoints", "models")
    needed = set()
    if os.path.isdir(src):
        for sub in os.listdir(src):
            sub_path = os.path.join(src, sub)
            if not os.path.isdir(sub_path):
                continue
            for d in os.listdir(sub_path):
                if d in _DOWNLOADABLE_DESCRIPTORS:
                    needed.add(d)
    return [d for d in _DOWNLOADABLE_DESCRIPTORS if d in needed]


def _run_in_runtime_env(cmd, cwd):
    """bash -c 'source conda.sh && conda activate <env> && <cmd>'."""
    full = f"source {CONDA_SH} && conda activate {RUNTIME_ENV} && {cmd}"
    return subprocess.run(["bash", "-c", full], cwd=cwd, capture_output=True, text=True)


def _read_columns(path):
    cols = []
    with open(path) as f:
        next(f)  # header
        for line in f:
            line = line.strip()
            if line:
                cols.append(line.split(",", 1)[0])
    return cols


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

    in_csv   = "model/framework/examples/run_input.csv"
    out_csv  = "model/framework/examples/run_output.csv"
    cols_csv = "model/framework/columns/run_columns.csv"

    # Descriptor weights live in $HOME/.lazyqsar/ (lazyqsar's default). Materialise
    # the per-pathogen subset on demand if a sentinel weight is missing.
    needed = _descriptors_needed(fork)
    sentinel_name = (
        f"{needed[0]}_mp.pt" if needed and needed[0] == "chemeleon"
        else f"{needed[0]}_encoder.onnx" if needed else None
    )
    sentinel = os.path.expanduser(f"~/.lazyqsar/{sentinel_name}") if sentinel_name else None
    if needed and not os.path.exists(sentinel):
        print(f"[0/4] descriptor weights missing — running lazyqsar setup --only {','.join(needed)}...")
        res = _run_in_runtime_env(
            f"lazyqsar setup --descriptors --only {','.join(needed)}",
            cwd=fork,
        )
        if res.returncode != 0:
            sys.stdout.write(res.stdout)
            sys.stderr.write(res.stderr)
            sys.exit("FAIL: lazyqsar setup failed.")

    print(f"[1/4] bash run.sh -> {out_csv}")
    res = _run_in_runtime_env(
        f"bash model/framework/run.sh model/framework {in_csv} {out_csv}",
        cwd=fork,
    )
    if res.returncode != 0:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        sys.exit("FAIL: run.sh failed.")
    if not os.path.exists(os.path.join(fork, out_csv)):
        sys.exit("FAIL: run_output.csv not produced.")

    print(f"[2/4] columns match run_columns.csv?")
    with open(os.path.join(fork, out_csv)) as f:
        first = f.readline().strip()
    out_cols = first.split(",")
    expected = _read_columns(os.path.join(fork, cols_csv))
    if out_cols != expected:
        sys.exit(f"FAIL: columns mismatch.\n  got:      {out_cols}\n  expected: {expected}")

    print(f"[3/4] values in [0, 1]?")
    import pandas as pd
    df = pd.read_csv(os.path.join(fork, out_csv))
    vmin, vmax = float(df.values.min()), float(df.values.max())
    if not (0.0 <= vmin and vmax <= 1.0):
        sys.exit(f"FAIL: values out of range. min={vmin} max={vmax}")

    print(f"[4/4] reproducibility (byte-identical re-run)?")
    # ersilia-pack-utils' write_out dispatches on the trailing .csv/.bin
    # extension, so the verify-run output must keep .csv at the end.
    tmp = out_csv.replace(".csv", ".check.csv")
    res = _run_in_runtime_env(
        f"bash model/framework/run.sh model/framework {in_csv} {tmp}",
        cwd=fork,
    )
    if res.returncode != 0:
        sys.exit(f"FAIL: 2nd run failed.\n{res.stderr}")
    a = os.path.join(fork, out_csv)
    b = os.path.join(fork, tmp)
    diff = subprocess.run(["diff", a, b], capture_output=True, text=True)
    if os.path.exists(b):
        os.remove(b)
    if diff.returncode != 0:
        sys.exit(f"FAIL: outputs differ on re-run.\n{diff.stdout}")

    print()
    print("=" * 60)
    print(f"PASS: {len(df)} rows x {len(out_cols)} columns, all in [0,1], reproducible.")
    print(f"Next:  python scripts/04_publish_pathogen.py --pathogen {args.pathogen}")


if __name__ == "__main__":
    main()
