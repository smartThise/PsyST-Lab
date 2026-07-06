# pi-release-exp

> Prompt-stage framework for the **PI-release** study.
> Tests whether single-message interventions can release an LLM from
> **proactive interference (PI)**, and measures how.
>
> Based on [arXiv:2506.08184](https://arxiv.org/abs/2506.08184)
> (*Unable to Forget*). Research design: [`../working_memory/think1.md`](../working_memory/think1.md).

This is a **standalone git repo**, independent of `mynotebook`'s main repo.

---

## What this does

Each run sends the model a high-interference key-value stream (same key updated
many times), asks for the most recent value per key, and measures whether a
given prompt-level **intervention** helps the model retrieve the right answer.

13 intervention groups (matching think1.md):

| group | what it injects |
|---|---|
| **G0** baseline | bare stream + query |
| **G1** semantic-forget | natural-language "ignore prior values" |
| **G2** mock-qa-reset | fake User→Assistant→User turn (paper's winner) |
| **G3** syntactic-cliff | `};}}}---===---%0A%0A<<<` symbol walls |
| **G4** glitch-tokens | `SolidGoldMagikarp` family, high-norm rare tokens |
| **G5** unicode-bytes | RTL override / zero-width / null / combining chars |
| **G6** self-generation | instructs the model to emit disruption tokens, then answer |
| **G7** query-engineering | recency-anchored phrasing + forced answer prefix |
| **S3** stack | mock-QA + cliff + glitch |
| **S5** stack | all 7 classes at once (max firepower) |

Three metrics per group:

- **RE** (Release Efficiency) — accuracy gain over baseline. How much the intervention helps.
- **CP** (Context Preservation) — can the model still answer an unrelated prior fact after the intervention? Tells *release* apart from *crash*.
- **Robustness Δ** — does deleting 1 character collapse the effect? Tells *deep dynamics* apart from *fragile token-exploit*.

---

## Quick start

```bash
# 0. use a venv (optional but recommended)
python -m venv .venv && source .venv/bin/activate

# 1. install deps (requests + pyyaml only)
pip install -r requirements.txt

# 2. configure API credentials
cp config/config.example.yaml config/config.yaml
#   then edit config.yaml: set api_key, model, base_url

# 3. run the experiment (all enabled groups)
python scripts/run_all.py
#   or a subset:
python scripts/run_all.py --groups G0 G2 G4

# 4. open the dashboard
python dashboard/server.py
#   -> http://127.0.0.1:8765 opens automatically
```

---

## Layout

```
pi-release-exp/
├── config/
│   ├── config.example.yaml    # API config template (copy to config.yaml)
│   ├── config.yaml            # YOUR secrets — gitignored
│   └── experiment.yaml        # PI params, groups, eval settings
├── src/
│   ├── api_client.py          # OpenAI-compatible client + retry/backoff
│   ├── pi_test.py             # PI stress-test stream generator
│   ├── groups.py              # the 13 prompt templates (registry)
│   ├── metrics.py             # answer parsing + RE/CP/Robustness
│   ├── runner.py              # orchestrates a run
│   └── utils.py
├── scripts/
│   └── run_all.py             # CLI entry point
├── dashboard/
│   ├── server.py              # zero-dep stdlib HTTP server
│   ├── index.html             # dashboard UI
│   ├── style.css              # dark theme
│   └── app.js                 # data fetch + Chart.js rendering
├── data/
│   ├── glitch_tokens.txt      # known glitch-token starter list
│   └── word_categories.json   # category word lists for PI values
├── runs/                      # outputs (gitignored) — one dir per run_tag
└── README.md
```

---

## Configuring an experiment

Edit [`config/experiment.yaml`](config/experiment.yaml):

```yaml
pi_test:
  n_keys: 3              # keys tracked
  updates_per_key: 80    # interference load (drives baseline accuracy -> ~0)
  n_trials: 10           # distinct streams per group
  seed: 42

eval:
  k_repeats: 5             # API calls per (group, trial)
  measure_cp: true
  measure_robustness: true

groups:
  - { id: G0, enabled: true }
  - { id: G4, enabled: true }
  # ... enable/disable to scope a run
```

Per-group generation overrides (e.g. G6 needs higher temperature) live in
`src/groups.py:OVERRIDES`.

---

## Outputs

Each run lands in `runs/<tag>/` where `<tag>` = `<timestamp>_<model>`:

- `run_config.json` — full snapshot (api key stripped)
- `results.jsonl` — one record per `(group, trial, call-type)`
- `summary.json` — aggregated per-group metrics; **this is what the dashboard reads**

---

## Dashboard

```bash
python dashboard/server.py
```

Zero external dependencies (uses `http.server` from the stdlib). The only
third-party piece is Chart.js, loaded from CDN by `index.html` (needs internet
on first open).

Shows:
- KPI cards: baseline accuracy, best RE, best group, mean CP
- Bar chart: accuracy + RE per group
- Bar chart: CP + robustness Δ per group
- Sortable per-group table with color coding
- Per-trial record table (latest 200 rows)

A run selector at the top lets you compare across historical runs.

---

## Adding a new intervention

1. Write a builder in [`src/groups.py`](src/groups.py):
   ```python
   def g8(test, seed=0):
       q = build_base_query(test.keys)
       return f"...your message..."
   ```
2. Register it: add `"G8": g8` to `REGISTRY`.
3. Add a row to `config/experiment.yaml` under `groups:`.
4. (Optional) add generation overrides to `OVERRIDES`.

The runner and dashboard pick it up automatically.

---

## Cost notes

At defaults (3 keys × 80 updates, 10 trials, k=5, CP + robustness on),
each enabled group costs ~`n_trials × (k + 2)` API calls ≈ **70 calls**.
A full G0–G7 + S3 run is ~**560 calls**. On `gpt-4o-mini`-class models this
is well under US$1 total; on stronger models, scale `n_trials` / `k_repeats`
down first.

---

## Relation to the mechanism stage (think2)

This prompt stage produces two things that feed the next (white-box) stage:

1. **Top-performing interventions** — to be replayed on an open-weights model
   while logging attention, to localize which heads/layers they activate.
2. **Differential candidates** — interventions that help under PI but not on
   easy inputs (the "PI fingerprint").

The bridge: prompt-stage top variants should activate the same heads that
mechanism-stage patching independently identifies as the release circuit.

---

## License & citation

Experiment code: MIT-style, do what you want.
The PI-LLM paradigm is from Wang & Sun, *Unable to Forget*, arXiv:2506.08184 —
please cite them if you build on this.
