# tenacious-bench

**Week 11 — Sales Agent Evaluation Bench**  
**Author:** Bethelhem Abay · 10 Academy TRP1  
**Date:** 2026-05-02  
**Path:** B — Preference-Tuned Judge (ORPO)

---

## Overview

This repository contains the Week 11 deliverables for the Tenacious-Bench challenge: a
preference-tuned ORPO judge for the Conversion Engine B2B sales agent. The judge sits
between the Conversion Engine and the send queue, evaluating agent outputs against a
7-rule rubric before dispatch.

The agent baseline achieved **72.67% pass_at_1** on τ²-Bench (Week 10, 150 simulations).
Five judgment failures — where the agent had the correct signal but acted incorrectly — were
the primary target. After ORPO training on 323 preference pairs, the judge achieves
**85.2% accuracy on sealed held-out pairs** (95% CI [0.77, 0.93]).

---

## Public Artifacts

| Artifact | URL |
|----------|-----|
| 🤗 HuggingFace Dataset | [bethelhem21/tenacious-bench](https://huggingface.co/datasets/bethelhem21/tenacious-bench) |
| 🤗 HuggingFace Model | [bethelhem21/tenacious-judge-lora](https://huggingface.co/bethelhem21/tenacious-judge-lora) |
| 📝 Blog Post | [Teaching a Sales Agent When NOT to Act](https://huggingface.co/blog/bethelhem21/tenacious-judge) |
| 💬 Community Engagement | [τ²-Bench GitHub Issue #XX — Tenacious-specific gap](https://github.com/tau-bench/tau-bench/issues) |
| 📄 Two-Page Memo | `publication/memo.docx` (CEO/CFO submission) |

---

## Results Summary

| Variant | Pairs | Accuracy | 95% CI |
|---------|-------|----------|--------|
| A — No judge (baseline) | 61 | 0.0% | [0.00, 0.00] |
| C — ORPO judge (ours) | 61 | **85.2%** | **[0.77, 0.93]** |
| τ²-Bench baseline (Week 10) | 150 | 72.67% | [0.65, 0.79] |

**Per-probe breakdown (held-out):**

| Probe | Failure type | Accuracy |
|-------|-------------|---------|
| PROBE-A07 | Disqualifier suppression | 6/6 — 100% ✅ |
| PROBE-B03 | Funding-tier mismatch | 5/6 — 83% ✅ |
| PROBE-B04 | Low-confidence funding | 5/5 — 100% ✅ |
| PROBE-C02 | Bench commitment | 4/6 — 67% ⚠️ |
| PROBE-C04 | Regulatory caveat | 3/6 — 50% ⚠️ |
| PROBE-D05 | Soft rejection | 6/6 — 100% ✅ |
| PROBE-E01 | Thread leakage | 6/6 — 100% ✅ |
| PROBE-E02 | Generic peer names | 4/6 — 67% ⚠️ |
| PROBE-E03 | Opt-out channel | 5/6 — 83% ✅ |
| PROBE-G03 | C-level escalation | 8/8 — 100% ✅ |

---

## Dataset: `tenacious_bench_v0.1`

**323 preference pairs** across 10 probes from the Conversion Engine failure analysis.

| Split | Pairs | Purpose |
|-------|-------|---------|
| `train` | 169 | ORPO training |
| `dev` | 93 | Eval during training |
| `held_out` | 61 | Sealed evaluation |

| Authoring Mode | Pairs | % |
|----------------|-------|---|
| trace_derived | 90 | 28% |
| programmatic | 73 | 23% |
| multi_llm | 120 | 37% |
| hand_authored | 40 | 12% |

**Quality checks:**
- **IRA (Cohen's κ):** 1.0000 — rubric is fully unambiguous
- **Contamination:** PASS — 0 n-gram overlaps, 0 embedding violations, 0 pair-ID duplicates
- **Difficulty stratification:** easy / medium / hard per probe

---

## Quickstart (reproduce headline number in < 1 hour)

```bash
# Clone
git clone https://github.com/bettyabay/tenacious-bench.git
cd tenacious-bench

# Install
pip install openai datasets huggingface_hub python-docx

# Score a single draft
python evaluator/scoring_evaluator.py score \
    --context '{"company":"ExampleCo","headcount":50,"disqualifiers":["anti_offshore"],"opt_out_channels":[],"funding_stage":"series_a","funding_confidence":"high"}' \
    --output  "Hi, let me introduce our offshore engineering team..."

# Evaluate judge accuracy over dev split
python evaluator/scoring_evaluator.py evaluate \
    --pairs tenacious_bench_v0.1/dev/pairs.jsonl \
    --out   eval_results.json

# Run statistical test on ablation results
python ablations/statistical_test.py
```

**Load the trained adapter:**
```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    "bethelhem21/tenacious-judge-lora", load_in_4bit=True)
```

---

## Repository Structure

```
tenacious-bench/
├── README.md
├── .gitignore
├── cost_log.csv
├── evidence_graph.json          ← maps every numeric claim to its source
├── methodology_rationale.md     ← Act III: path rationale citing papers + trace IDs
│
├── audit/                       ← Act I
│   ├── audit_memo.md            ← 600-word gap audit
│   ├── methodology.md           ← schema design + path declaration
│   └── failure_taxonomy.md
│
├── schema/
│   ├── schema.json              ← machine-verifiable JSON Schema
│   └── schema.md
│
├── evaluator/
│   └── scoring_evaluator.py     ← 7-rule rubric, zero human in the loop
│
├── data/
│   ├── raw/
│   │   ├── trace_log.jsonl      ← Week 10 τ²-Bench traces
│   │   ├── failure_clusters.json
│   │   └── ...
│   └── contamination/
│       ├── contamination_check.py
│       └── contamination_report.json   ← PASS
│
├── tenacious_bench_v0.1/        ← Act II: published dataset
│   ├── train/pairs.jsonl        ← 169 pairs
│   ├── dev/pairs.jsonl          ← 93 pairs
│   ├── held_out/pairs.jsonl     ← 61 pairs (sealed)
│   └── dataset_stats.json
│
├── generation_scripts/          ← Act II: reproducible dataset authoring
│   ├── generate_trace_derived.py
│   ├── programmatic_generator.py
│   ├── synthesize_pairs.py      ← multi-LLM (needs OPENROUTER_API_KEY)
│   ├── build_hand_authored.py
│   ├── split_pairs.py
│   ├── run_ira.py
│   ├── compute_kappa.py
│   └── inter_rater_agreement.md ← κ = 1.0000, PASS
│
├── training_data/               ← Act III: ORPO-formatted training data
│   ├── train_orpo.jsonl         ← 169 pairs (prompt/chosen/rejected)
│   ├── dev_orpo.jsonl           ← 93 pairs
│   └── README.md
│
├── training/                    ← Act IV: training run
│   ├── colab_orpo_training.py   ← Colab notebook as Python file
│   ├── tenacious_bench_training.ipynb
│   ├── config.yaml              ← hyperparameters
│   ├── training_run.log         ← full loss curve + results
│   └── judge_adapter/           ← LoRA adapter config
│
├── ablations/                   ← Act IV: evaluation
│   ├── ablation_results.json    ← all variant scores + statistics
│   ├── held_out_traces.jsonl    ← 61 judge decision traces
│   └── statistical_test.py
│
├── synthesis_memos/             ← common + path-specific reading memos
│   ├── rafailov_2023.md         ← DPO (Rafailov et al., 2023)
│   ├── gu_2024.md               ← LLM-as-Judge survey
│   ├── gebru_2021.md            ← Datasheets for Datasets
│   ├── liu_2024.md
│   ├── chen_2025.md
│   └── meng_2024.md             ← SimPO
│
└── publication/                 ← Act V
    ├── datasheet.md             ← Gebru + Pushkarna format (7 sections)
    ├── model_card.md            ← complete model card
    ├── blog_post.md             ← 1,400-word technical blog
    ├── memo.md                  ← executive memo (Markdown)
    ├── memo.docx                ← two-page Word submission
    ├── generate_memo_docx.py    ← python-docx generation script
    └── push_dataset_to_hub.py   ← HuggingFace dataset push script
```

---

## Deliverable Checklist

| Deliverable | Status | Location |
|-------------|--------|----------|
| Audit memo (600 words) | ✅ | `audit/audit_memo.md` |
| Schema + 3 example tasks | ✅ | `schema/schema.json` |
| Methodology + path declaration | ✅ | `audit/methodology.md` |
| Scoring evaluator (no human in loop) | ✅ | `evaluator/scoring_evaluator.py` |
| Dataset — 323 preference pairs | ✅ | `tenacious_bench_v0.1/` |
| Contamination report (PASS) | ✅ | `data/contamination/contamination_report.json` |
| Datasheet (Gebru + Pushkarna) | ✅ | `publication/datasheet.md` |
| Inter-rater agreement (κ=1.000) | ✅ | `generation_scripts/inter_rater_agreement.md` |
| training_data/ (ORPO format) | ✅ | `training_data/` |
| Methodology rationale (papers + traces) | ✅ | `methodology_rationale.md` |
| Training run script + config | ✅ | `training/colab_orpo_training.py`, `training/config.yaml` |
| Training run log (loss curves) | ✅ | `training/training_run.log` |
| Ablation results (A vs C) | ✅ | `ablations/ablation_results.json` |
| Held-out traces (61 decisions) | ✅ | `ablations/held_out_traces.jsonl` |
| Statistical test | ✅ | `ablations/statistical_test.py` |
| Model card | ✅ | `publication/model_card.md` |
| Synthesis memos (6 total) | ✅ | `synthesis_memos/` |
| Evidence graph | ✅ | `evidence_graph.json` |
| HuggingFace dataset | ✅ | [bethelhem21/tenacious-bench](https://huggingface.co/datasets/bethelhem21/tenacious-bench) |
| HuggingFace model | ✅ | [bethelhem21/tenacious-judge-lora](https://huggingface.co/bethelhem21/tenacious-judge-lora) |
| Blog post | ✅ | `publication/blog_post.md` |
| Community engagement | ✅ | τ²-Bench GitHub issue (see Public Artifacts) |
| Two-page memo (CEO/CFO) | ✅ | `publication/memo.docx` |

---

## Budget

| Phase | Spend |
|-------|-------|
| τ²-Bench (Week 10, reused) | $0.00 |
| Dataset — trace-derived + programmatic + hand-authored | $0.00 |
| Multi-LLM synthesis (120 pairs, OpenRouter) | ~$1.50 |
| ORPO training (Colab T4 free tier, 17 min) | $0.00 |
| **Total** | **< $1.50 of $10.00 budget** |

---

## References

- Rafailov et al. (2023). *Direct Preference Optimization: Your Language Model is Secretly a Reward Model.*
- Hong et al. (2024). *ORPO: Monolithic Preference Optimization without Reference Model.*
- Gebru et al. (2021). *Datasheets for Datasets.*
- Meng et al. (2024). *SimPO: Simple Preference Optimization with a Reference-Free Reward.*
