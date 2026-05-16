# chembl-antimicrobial-hub-incorporation

Coordinator repo for packaging the 15 pathogen-specific antimicrobial-activity QSAR models from [`ersilia-os/chembl-antimicrobial-models`](https://github.com/ersilia-os/chembl-antimicrobial-models) into the [Ersilia Model Hub](https://github.com/ersilia-os/ersilia). One Hub model per pathogen (`eosXXXX`).

## What lives here

- [CLAUDE.md](CLAUDE.md) — overall workflow, monitoring table for the 15 pathogens, and the key principles that apply to every per-pathogen build.
- [docs/per-pathogen-runbook.md](docs/per-pathogen-runbook.md) — full step-by-step procedure (steps 0–v) for one pathogen, distilled from the abaumannii / eos21dr build session.
- [scripts/](scripts/) — placeholder for helper utilities (bulk issue creation, fork management, monitoring-table updates).
- `eos*/` — per-pathogen forks cloned in-place; each one is its own git repo (`arnaucoma24/eosXXXX`) and is `.gitignore`d from this coordinator's git.

The actual QSAR weights, training data, and consensus-scoring logic all live in [`ersilia-os/chembl-antimicrobial-models`](https://github.com/ersilia-os/chembl-antimicrobial-models) (referenced via `$PATH_TO_CAMM`). This repo doesn't store data or run analyses — it's a workspace + documentation hub.

## Getting started

```bash
git clone git@github.com:ersilia-os/chembl-antimicrobial-hub-incorporation.git
cd chembl-antimicrobial-hub-incorporation

export PATH_TO_CAMM=/path/to/your/clone/of/chembl-antimicrobial-models
```

Then open [CLAUDE.md](CLAUDE.md) and pick a pathogen to work on from the monitoring table.

## About the Ersilia Open Source Initiative

The [Ersilia Open Source Initiative](https://ersilia.io) is a tech-nonprofit organisation fuelling sustainable research in the Global South. Ersilia's main asset is the [Ersilia Model Hub](https://github.com/ersilia-os/ersilia), an open-source repository of AI/ML models for antimicrobial drug discovery.

![Ersilia Logo](assets/Ersilia_Brand.png)
