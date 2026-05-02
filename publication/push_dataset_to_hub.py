"""
push_dataset_to_hub.py — Push Tenacious-Bench v0.1 to HuggingFace Hub

Usage:
    python publication/push_dataset_to_hub.py --token hf_xxxx
    python publication/push_dataset_to_hub.py --token hf_xxxx --repo bethelhem21/tenacious-bench
"""

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLITS = {
    "train"    : REPO_ROOT / "tenacious_bench_v0.1" / "train"    / "pairs.jsonl",
    "dev"      : REPO_ROOT / "tenacious_bench_v0.1" / "dev"      / "pairs.jsonl",
    "held_out" : REPO_ROOT / "tenacious_bench_v0.1" / "held_out" / "pairs.jsonl",
}

DATASET_CARD = """---
language:
- en
license: mit
task_categories:
- text-classification
tags:
- orpo
- preference
- judge
- sales-outreach
- b2b
- evaluation
size_categories:
- n<1K
---

# Tenacious-Bench v0.1

A preference dataset for training and evaluating a B2B sales outreach judge.
Built as part of the TRP1 Programme, Week 11.

## Dataset Description

323 preference pairs across 10 failure probes derived from a real B2B sales
agent (Tenacious Conversion Engine). Each pair contains a prospect context,
a chosen (correct) agent action, and a rejected (incorrect) agent action.

## Probes

| Probe | Failure type | Severity |
|-------|-------------|----------|
| A07 | Anti-offshore disqualifier ignored | Tier 1 |
| E01 | Thread context leaked | Tier 1 |
| E02 | Generic peer company names | Tier 2 |
| E03 | Opt-out channel ignored | Tier 1 |
| G03 | C-level escalation missed | Tier 2 |
| B03 | Funding-tier mismatch | Tier 2 |
| B04 | Low-confidence funding cited as fact | Tier 2 |
| C02 | Bench commitment ignored | Tier 2 |
| C04 | Regulatory caveat omitted | Tier 2 |
| D05 | Soft rejection doubled down | Tier 3 |

## Splits

| Split | Pairs |
|-------|-------|
| train | 169 |
| dev | 93 |
| held_out | 61 |
| **Total** | **323** |

## Authoring Modes

- **trace_derived** (90): Extracted from Week 10 agent traces
- **programmatic** (73): Parameter sweeps over context templates
- **multi_llm** (120): GPT-4o, DeepSeek, Llama-3 generating variants
- **hand_authored** (40): Manually written boundary cases

## Schema

```json
{
  "pair_id": "A07-001",
  "probe_id": "PROBE-A07",
  "failure_type": "judgment",
  "severity_tier": 1,
  "authoring_mode": "trace_derived",
  "context": {
    "company": "...", "headcount": 200,
    "disqualifiers": ["anti_offshore"],
    "opt_out_channels": [], "recipient_role": "cto",
    "funding_stage": "series_b", "funding_confidence": "high",
    "available_signals": {}
  },
  "chosen":   {"action": "suppress", "output": "", "rationale": "..."},
  "rejected": {"action": "send",     "output": "...", "rationale": "..."},
  "difficulty": "easy",
  "split": "train"
}
```

## Quality Checks

- **IRA (Cohen's kappa):** 1.0000 — rubric is fully unambiguous
- **Contamination:** PASS — 0 n-gram overlap, 0 pair-ID duplicates
- **Difficulty stratification:** easy / medium / hard per probe

## Associated Model

Trained ORPO judge: [bethelhem21/tenacious-judge-lora](https://huggingface.co/bethelhem21/tenacious-judge-lora)
- Held-out accuracy: 85.2% (95% CI [0.77, 0.93])
- Base model: Qwen2.5-1.5B-Instruct
- Method: ORPO, 200 steps

## Citation

```
@misc{tenacious-bench-2026,
  author = {Bethelhem Abay},
  title  = {Tenacious-Bench v0.1: A Preference Dataset for B2B Sales Outreach Evaluation},
  year   = {2026},
  url    = {https://huggingface.co/datasets/bethelhem21/tenacious-bench}
}
```
"""


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", required=True, help="HuggingFace write token")
    parser.add_argument("--repo",  default="bethelhem21/tenacious-bench",
                        help="HuggingFace repo id (default: bethelhem21/tenacious-bench)")
    parser.add_argument("--private", action="store_true", help="Make repo private")
    args = parser.parse_args()

    from datasets import Dataset, DatasetDict
    from huggingface_hub import HfApi

    # Load all splits
    print("Loading splits...")
    dataset_dict = {}
    for split_name, path in SPLITS.items():
        rows = load_jsonl(path)
        # Flatten context dict into top-level columns for HF viewer compatibility
        flat_rows = []
        for r in rows:
            ctx = r.get("context", {})
            flat = {
                "pair_id"       : r.get("pair_id", ""),
                "probe_id"      : r.get("probe_id", ""),
                "failure_type"  : r.get("failure_type", ""),
                "severity_tier" : r.get("severity_tier", 0),
                "authoring_mode": r.get("authoring_mode", ""),
                "difficulty"    : r.get("difficulty", ""),
                "split"         : r.get("split", split_name),
                "company"       : ctx.get("company", ""),
                "headcount"     : ctx.get("headcount", 0),
                "funding_stage" : ctx.get("funding_stage", ""),
                "funding_confidence": ctx.get("funding_confidence", ""),
                "disqualifiers" : json.dumps(ctx.get("disqualifiers", [])),
                "opt_out_channels": json.dumps(ctx.get("opt_out_channels", [])),
                "recipient_role": ctx.get("recipient_role", ""),
                "chosen_action" : r.get("chosen", {}).get("action", ""),
                "chosen_output" : r.get("chosen", {}).get("output", ""),
                "chosen_rationale": r.get("chosen", {}).get("rationale", ""),
                "rejected_action": r.get("rejected", {}).get("action", ""),
                "rejected_output": r.get("rejected", {}).get("output", ""),
                "rejected_rationale": r.get("rejected", {}).get("rationale", ""),
            }
            flat_rows.append(flat)
        dataset_dict[split_name] = Dataset.from_list(flat_rows)
        print(f"  {split_name}: {len(flat_rows)} pairs")

    ds = DatasetDict(dataset_dict)
    print(f"\nTotal: {sum(len(v) for v in dataset_dict.values())} pairs")

    # Push to hub
    print(f"\nPushing to {args.repo}...")
    ds.push_to_hub(
        args.repo,
        token   = args.token,
        private = args.private,
    )
    print(f"Dataset pushed.")

    # Upload dataset card
    print("Uploading dataset card...")
    api = HfApi()
    api.upload_file(
        path_or_fileobj = DATASET_CARD.encode("utf-8"),
        path_in_repo    = "README.md",
        repo_id         = args.repo,
        repo_type       = "dataset",
        token           = args.token,
        commit_message  = "Add dataset card",
    )

    print(f"\nDone! Dataset live at:")
    print(f"  https://huggingface.co/datasets/{args.repo}")


if __name__ == "__main__":
    main()
