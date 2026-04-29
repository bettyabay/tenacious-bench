# tenacious-bench

**Week 11 — Sales Agent Evaluation Bench**
**Author:** Bethelhem Abay · 10 Academy TRP1
**Date:** 2026-04-29
**Path:** B — Preference-Tuned Judge (DPO)

---

## Overview

This repository contains the Week 11 deliverables for the Tenacious-Bench challenge: a preference-tuned DPO judge for the Conversion Engine B2B sales agent. The judge scores agent outputs before dispatch and blocks actions that violate suppression, escalation, thread-isolation, or generation-quality rules.

The agent baseline achieved **72.67% pass_at_1** on τ²-Bench (Week 10, 150 simulations). The 5 judgment failures — where the agent *has* the correct signal but acts incorrectly — are the primary target. Path B (DPO) was selected over SFT (Path A) and PRM (Path C) because judgment gaps cannot be fixed by teaching *what to write*; they require learning *when not to write*.

---

## Status

| Deliverable | Status | Location |
|-------------|--------|----------|
| Failure analysis (audit memo) | ✅ Done | `audit/audit_memo.md` |
| Path declaration + justification | ✅ Done | `audit/methodology.md` |
| Failure taxonomy (Tier 1–4) | ✅ Done | `audit/failure_taxonomy.md` |
| Judge preference dataset schema | ✅ Done | `schema/schema.md`, `schema/schema.json` |
| Judge inference wrapper | ✅ Done | `evaluator/scoring_evaluator.py` |
| Dataset — 203 preference pairs | ✅ Done | `tenacious_bench_v0.1/` |
| Contamination check (PASS) | ✅ Done | `data/contamination/contamination_report.json` |
| Dataset card (Gebru + Pushkarna) | ✅ Done | `publication/datasheet.md` |
| Inter-rater agreement scaffold | ✅ Done | `generation_scripts/inter_rater_agreement.md` |
| Synthesis memos (2 complete) | ✅ Done | `synthesis_memos/` |
| Cost log | ✅ Done | `cost_log.csv` |
| DPO training config | ✅ Done | `training/config.yaml` |
| Multi-LLM synthesis script | ⚠️ Ready to run | `generation_scripts/synthesize_pairs.py` |
| DPO training (Colab T4) | ⏳ Next | `training/train_judge.py` |
| Ablation results | ⏳ After training | `ablations/` |
| HuggingFace adapter | ⏳ After training | `training/judge_adapter/` |

---

## Dataset: `tenacious_bench_v0.1`

**203 preference pairs** across 10 probes from the Conversion Engine failure analysis.

| Split | Count | % |
|-------|-------|---|
| `train` | 124 | 61% |
| `dev` | 69 | 34% |
| `held_out` | 10 | 5% — sealed until final eval |

| Authoring Mode | Count | % |
|----------------|-------|---|
| trace_derived | 90 | 44% |
| programmatic | 73 | 36% |
| hand_authored | 40 | 20% |

| Probe | Pairs | Failure Type | Tier |
|-------|-------|-------------|------|
| PROBE-A07 | 22 | Judgment | 1 |
| PROBE-E01 | 19 | Judgment | 1 |
| PROBE-E02 | 18 | Judgment | 3 |
| PROBE-E03 | 21 | Judgment | 4 |
| PROBE-G03 | 31 | Judgment | 2 |
| PROBE-B03 | 19 | Generation | 2 |
| PROBE-B04 | 17 | Generation | 2 |
| PROBE-C02 | 19 | Generation | 3 |
| PROBE-C04 | 18 | Generation | 3 |
| PROBE-D05 | 19 | Generation | 1 |

---

## Setup

```bash
# Clone
git clone <repo-url>
cd tenacious-bench

# Install dependencies
pip install openai          # OpenRouter is OpenAI-compatible

# Set API key (required for scoring and multi-LLM synthesis)
export OPENROUTER_API_KEY="sk-or-v1-..."
```

### Score a single draft output

```bash
python evaluator/scoring_evaluator.py score \
    --context path/to/context.json \
    --output  path/to/draft.txt
```

### Evaluate judge accuracy over the dataset

```bash
python evaluator/scoring_evaluator.py evaluate \
    --pairs tenacious_bench_v0.1/dev/pairs.jsonl \
    --out   eval_results.json
```

### Re-generate the dataset from scratch

```bash
# Mode 1 — trace-derived (90 pairs)
python generation_scripts/generate_trace_derived.py

# Mode 2 — programmatic (73 pairs)
python generation_scripts/programmatic_generator.py
python generation_scripts/programmatic_generator_ext.py

# Mode 3 — multi-LLM (requires OPENROUTER_API_KEY)
python generation_scripts/synthesize_pairs.py

# Mode 4 — hand-authored (40 pairs)
python generation_scripts/build_hand_authored.py
python generation_scripts/build_hand_authored_ext.py

# Split into tenacious_bench_v0.1/
python generation_scripts/split_pairs.py

# Contamination check
python data/contamination/contamination_check.py
```

### Train the judge (Google Colab T4)

Upload `training/` to Colab and run:
```bash
python training/train_judge.py --config training/config.yaml
```

---

## Repository Structure

```
tenacious-bench/
├── README.md
├── .gitignore
├── cost_log.csv
│
├── audit/                        # Act I — failure analysis
│   ├── audit_memo.md
│   ├── methodology.md
│   └── failure_taxonomy.md
│
├── schema/                       # Dataset schema
│   ├── schema.json               # JSON Schema draft-07
│   └── schema.md                 # Human-readable schema doc
│
├── evaluator/                    # Judge inference wrapper
│   └── scoring_evaluator.py
│
├── data/                         # Raw inputs + contamination
│   ├── raw/
│   │   ├── trace_log.jsonl       # Week 10 τ²-Bench trace
│   │   ├── failure_clusters.json # Task failure analysis
│   │   ├── task_probe_map.json   # task_id → probe_id (fill in)
│   │   ├── probe_library.md
│   │   ├── style_guide.md
│   │   └── sales_deck.md
│   └── contamination/
│       ├── contamination_check.py
│       └── contamination_report.json   # PASS
│
├── tenacious_bench_v0.1/         # Published dataset
│   ├── train/pairs.jsonl         # 124 pairs
│   ├── dev/pairs.jsonl           # 69 pairs
│   ├── held_out/pairs.jsonl      # 10 pairs (sealed)
│   └── dataset_stats.json
│
├── generation_scripts/           # Reproducible dataset authoring
│   ├── generate_trace_derived.py
│   ├── programmatic_generator.py
│   ├── programmatic_generator_ext.py
│   ├── synthesize_pairs.py       # Multi-LLM (needs API key)
│   ├── build_hand_authored.py
│   ├── build_hand_authored_ext.py
│   ├── filter_with_judge.py
│   ├── split_pairs.py
│   ├── trace_derived.py          # τ²-Bench trace analyser
│   └── inter_rater_agreement.md
│
├── training/                     # DPO training (Colab T4)
│   ├── train_judge.py
│   ├── config.yaml
│   ├── training_run.log
│   └── judge_adapter/
│
├── ablations/
│   ├── ablation_results.json
│   ├── held_out_traces.jsonl
│   └── statistical_test.py
│
├── synthesis_memos/              # Common-reading memos
│   ├── rafailov_2023.md          # DPO paper
│   ├── gu_2024.md                # LLM-as-Judge survey
│   ├── gebru_2021.md
│   ├── liu_2024.md
│   ├── chen_2025.md
│   └── meng_2024.md
│
└── publication/
    ├── datasheet.md              # Gebru + Pushkarna format
    ├── model_card.md
    ├── blog_post.md
    └── memo.md
```

---

## What's Next

1. **Run multi-LLM synthesis** — `generation_scripts/synthesize_pairs.py` (needs `OPENROUTER_API_KEY`) to add ~50-75 more pairs and diversify authoring modes
2. **Inter-rater agreement** — sample 20 pairs, second-annotate with GPT-4o, compute Cohen's κ (target ≥ 0.80)
3. **DPO training on Colab T4** — run `training/train_judge.py` with `training/config.yaml`
4. **Ablation evaluation** — run judge on held_out slice after training, compare A/B/C variants
5. **Publish to HuggingFace** — adapter + dataset card

---

## Budget

| Phase | Spend |
|-------|-------|
| τ²-Bench (Week 10, reused) | $0.00 |
| Dataset synthesis (Modes 1, 2, 4) | $0.00 |
| Multi-LLM synthesis (Mode 3) | ~$1–2 |
| DPO training (Colab T4) | $0.00 |
| Final eval | ~$1–2 |
| **Total projected** | **$2–4 of $10** |
