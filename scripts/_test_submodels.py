#!/usr/bin/env python3
"""Per-sub-model consistency test (auxiliary; not in the 01-04 main flow).

For every sub-model under `<fork>/model/checkpoints/models/<sub>/`, run
lazyqsar.predict() in isolation (single-entry model_dir) and dump the
4-decimal-rounded prob_ranks to `tmp/<eosXXXX>_<sub>.csv`. Then compare
each isolated column against the same column in the fork's already-
generated `run_output.csv` (produced by 03_test_pathogen.py, where
lazyqsar runs with ALL sub-models in one batched dict call).

If the isolated and batched outputs ever diverge, this script catches
it (cross-talk between sub-models, descriptor caching bugs, hidden
shared state, etc.).

Exits non-zero on any sub-model mismatch or run failure.

Usage:
    conda activate cam-hub-inc
    python scripts/03_test_pathogen.py --pathogen abaumannii   # produces run_output.csv
    python scripts/_test_submodels.py  --pathogen abaumannii
"""

import argparse
import csv
import os
import subprocess
import sys

REPO_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY    = os.path.join(REPO_ROOT, "data", "00_registry.csv")
TMP_DIR     = os.path.join(REPO_ROOT, "tmp")
CONDA_SH    = os.environ.get(
    "CONDA_SH",
    os.path.expanduser("~/programs/miniconda3/etc/profile.d/conda.sh"),
)
RUNTIME_ENV = "cam-models-runtime"

_DOWNLOADABLE_DESCRIPTORS = ("chemeleon", "clamp", "cddd")


def _descriptors_needed(fork):
    """Subset of {chemeleon, clamp, cddd} that this fork's sub-models use."""
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
    full = f"source {CONDA_SH} && conda activate {RUNTIME_ENV} && {cmd}"
    return subprocess.run(["bash", "-c", full], cwd=cwd, capture_output=True, text=True)


def _ensure_descriptors(fork):
    needed = _descriptors_needed(fork)
    if not needed:
        return
    sentinel = os.path.join(
        fork, "model/checkpoints/featurizer_weights_home/.lazyqsar",
        f"{needed[0]}_mp.pt" if needed[0] == "chemeleon" else f"{needed[0]}_encoder.onnx",
    )
    if os.path.exists(sentinel):
        return
    print(f"[setup] descriptor weights missing — running lazyqsar setup --only {','.join(needed)}...")
    res = _run_in_runtime_env(
        f"lazyqsar setup --descriptors --only {','.join(needed)} "
        f"--target-dir model/checkpoints/featurizer_weights_home/.lazyqsar",
        cwd=fork,
    )
    if res.returncode != 0:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        sys.exit("FAIL: lazyqsar setup failed.")


def _predict_isolated(fork, sub, out_csv):
    """Run lazyqsar.predict() in isolation for a single sub-model.

    Mirrors the env-var dance in eos21dr/model/framework/code/main.py:12-23 —
    MPLCONFIGDIR and HOME must be set BEFORE the lazyqsar import. We do that
    inside the snippet itself (each invocation is a fresh Python process).
    """
    sub_path = os.path.join(fork, "model", "checkpoints", "models", sub)
    in_csv   = os.path.join(fork, "model/framework/examples/run_input.csv")
    raw_csv  = out_csv + ".raw"
    snippet = f"""
import os, atexit, shutil, tempfile
_mpl = tempfile.mkdtemp(prefix='mpl_')
os.environ['MPLCONFIGDIR'] = _mpl
atexit.register(lambda: shutil.rmtree(_mpl, ignore_errors=True))
os.environ['HOME'] = {os.path.join(fork, 'model/checkpoints/featurizer_weights_home')!r}

from lazyqsar.api.classifier_predict import predict as lqsar_predict
import pandas as pd

lqsar_predict(
    model_dir={{{sub!r}: {sub_path!r}}},
    input_csv={in_csv!r},
    output_csv={raw_csv!r},
    predict_type='rank',
)
df = pd.read_csv({raw_csv!r})
df[{sub!r}] = df[{sub!r}].round(4)
df.to_csv({out_csv!r}, index=False)
os.remove({raw_csv!r})
"""
    res = _run_in_runtime_env(f"python <<'PYEOF'\n{snippet}\nPYEOF", cwd=fork)
    return res


def _compare(sub, isolated_csv, batched_csv):
    """Return (passed: bool, detail: str). Exact equality on 4-decimal floats."""
    import pandas as pd
    iso = pd.read_csv(isolated_csv)
    bat = pd.read_csv(batched_csv)
    if sub not in bat.columns:
        return False, f"column {sub!r} missing from run_output.csv (columns: {list(bat.columns)})"
    if sub not in iso.columns:
        return False, f"column {sub!r} missing from isolated CSV (columns: {list(iso.columns)})"
    if len(iso) != len(bat):
        return False, f"row count mismatch (isolated={len(iso)} vs batched={len(bat)})"
    iso_col = iso[sub].round(4).tolist()
    bat_col = bat[sub].round(4).tolist()
    if iso_col != bat_col:
        diffs = [(i, a, b) for i, (a, b) in enumerate(zip(iso_col, bat_col)) if a != b]
        first = diffs[0]
        return False, f"{len(diffs)}/{len(iso_col)} rows differ; first @row {first[0]}: isolated={first[1]} batched={first[2]}"
    return True, f"{len(iso_col)} rows match"


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

    batched_csv = os.path.join(fork, "model/framework/examples/run_output.csv")
    if not os.path.exists(batched_csv):
        sys.exit(
            f"Missing {batched_csv}. Run `python scripts/03_test_pathogen.py "
            f"--pathogen {args.pathogen}` first to produce the batched golden output."
        )

    _ensure_descriptors(fork)

    models_dir = os.path.join(fork, "model/checkpoints/models")
    sub_models = sorted(
        d for d in os.listdir(models_dir)
        if os.path.isdir(os.path.join(models_dir, d))
    )
    if not sub_models:
        sys.exit(f"No sub-models found under {models_dir}")
    print(f"Found {len(sub_models)} sub-models for {args.pathogen} ({eosXXXX}): {sub_models}")

    os.makedirs(TMP_DIR, exist_ok=True)

    results = []
    for i, sub in enumerate(sub_models, 1):
        out_csv = os.path.join(TMP_DIR, f"{eosXXXX}_{sub}.csv")
        print(f"[{i}/{len(sub_models)}] {sub} -> {out_csv}")
        res = _predict_isolated(fork, sub, out_csv)
        if res.returncode != 0:
            sys.stdout.write(res.stdout)
            sys.stderr.write(res.stderr)
            results.append((sub, False, "isolated predict failed"))
            continue
        passed, detail = _compare(sub, out_csv, batched_csv)
        results.append((sub, passed, detail))
        print(f"        {'PASS' if passed else 'FAIL'}: {detail}")

    n_pass = sum(1 for _, ok, _ in results if ok)
    n_total = len(results)
    print()
    print("=" * 60)
    if n_pass == n_total:
        print(f"PASS: {n_pass}/{n_total} sub-models match.")
        return 0
    print(f"FAIL: {n_total - n_pass}/{n_total} sub-models differ — see tmp/{eosXXXX}_*.csv")
    for sub, ok, detail in results:
        if not ok:
            print(f"  - {sub}: {detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
