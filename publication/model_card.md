# Model Card — Tenacious Judge LoRA Adapter

**Status:** ⚠️ TO COMPLETE after training

---

## Model Details

| Field | Value |
|-------|-------|
| Base model | unsloth/llama-3-8b-bnb-4bit |
| Adapter type | LoRA (r=16) |
| Training method | DPO (β=0.1) |
| Training data | judge_pairs (200-300 pairs) |
| HuggingFace repo | TBD |

## Intended Use

Score B2B sales outreach drafts before dispatch. Block outputs that violate
suppression, escalation, thread-isolation, or generation-quality rules.

## Evaluation

| Metric | Value |
|--------|-------|
| Judge accuracy (held_out) | TBD |
| Cohen's κ | TBD |

## Limitations

<!-- Fill after training and eval -->

## How to Use

```python
# TODO: add inference example after adapter is trained
```
