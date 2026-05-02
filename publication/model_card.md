---
language:
- en
license: mit
base_model: unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit
tags:
- orpo
- preference-optimisation
- lora
- sales-outreach
- b2b
- judge
- tenacious
datasets:
- bethelhem21/tenacious-bench
---

# Model Card — Tenacious Judge LoRA Adapter

**HuggingFace repo:** [bethelhem21/tenacious-judge-lora](https://huggingface.co/bethelhem21/tenacious-judge-lora)  
**Base model:** `unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit`  
**Training dataset:** [bethelhem21/tenacious-bench](https://huggingface.co/datasets/bethelhem21/tenacious-bench)  
**Author:** Bethelhem Abay · TRP1 Programme, Week 11  
**Date:** 2026-05-02

---

## Model Details

| Field | Value |
|-------|-------|
| Base model | `Qwen2.5-1.5B-Instruct` (4-bit quantised via Unsloth) |
| Adapter type | LoRA (r=16, alpha=16, dropout=0) |
| Training method | ORPO — Odds-Ratio Preference Optimisation (Hong et al., 2024) |
| Trainable parameters | 18,087,936 (1.18% of total) |
| Training data | Tenacious-Bench v0.1 — 169 training pairs, 10 probes |
| Total training steps | 200 (10 epochs, batch size 8, seed 3407) |
| Hardware | Google Colab T4 (free tier) |
| Training time | ~17 minutes |
| Adapter size | ~74 MB |

---

## Intended Use

This adapter sits between the Tenacious Conversion Engine and the send queue, acting as a
**pre-send judge**. Before any B2B outreach email is dispatched, the judge evaluates the
proposed action against a 7-rule rubric and returns one of:

- **SUPPRESS** — disqualifier or opt-out signal present; block all outreach
- **ESCALATE** — C-level recipient at >2,000 headcount; route to human account exec
- **BLOCK** — thread leakage or low-confidence funding cited as fact
- **PENALISE** — generic peer company names (flag for human review)
- **PASS** — no rule violations detected; approve for dispatch

### In-scope use cases
- Blocking B2B outreach to prospects with anti-offshore, local-only, or do-not-contact flags
- Blocking emails to prospects who have opted out of the outreach channel
- Routing C-level enterprise outreach to human escalation
- Flagging low-confidence funding claims before they reach a prospect

### Out-of-scope use cases
- Multi-turn thread coherence evaluation (single-turn judge only)
- Timezone or send-window validation (not in training data)
- Regulated-industry caveat checking (finance, healthcare, defence)
- General-purpose email quality scoring

---

## The 7-Rule Rubric

Rules are applied in strict priority order:

1. **SUPPRESS** if any disqualifier is present (`anti_offshore`, `local_only`, `do_not_contact`)
2. **SUPPRESS** if the prospect has opted out of the outreach channel
3. **ESCALATE** if the recipient is C-level at a company with >2,000 employees
4. **BLOCK** if the output references content from a different thread
5. **BLOCK** if a funding amount is cited but `funding_confidence` is `low` or `insufficient_signal`
6. **PENALISE** if peer company names are generic or reused across prospects
7. **PASS** if none of the above conditions are triggered

---

## Training

**Method:** ORPO was chosen over DPO because it eliminates the reference model (saving 3–4 GB
VRAM on T4), combines SFT + preference loss in one pass, and outperforms DPO on datasets under
500 pairs (Hong et al., 2024). The training data is Tenacious-Bench v0.1, a preference dataset
of 323 pairs across 10 judgment and generation failure probes derived from Week 10 agent traces.

**Key training metrics:**

| Metric | Value |
|--------|-------|
| Start loss | 3.25 |
| Final train loss | 0.1411 |
| Final eval loss | 0.3851 |
| Loss reduction | 95.7% |
| Preference accuracy | 100% (reached step 40, held through step 200) |
| Rewards margin | 0.6934 |

---

## Evaluation Results

Evaluated on 61 sealed held-out pairs (all rejected outputs — cases where the Conversion
Engine made the wrong decision).

| Variant | Correct | Accuracy | 95% CI |
|---------|---------|----------|--------|
| No judge (baseline) | 0/61 | 0.0% | [0.00, 0.00] |
| ORPO judge (this model) | 52/61 | **85.2%** | **[0.77, 0.93]** |

**Per-probe breakdown:**

| Probe | Failure type | Judge accuracy |
|-------|-------------|---------------|
| PROBE-A07 | Disqualifier (anti_offshore) | 6/6 — 100% |
| PROBE-B03 | Funding-tier mismatch | 5/6 — 83% |
| PROBE-B04 | Low-confidence funding | 5/5 — 100% |
| PROBE-C02 | Bench commitment ignored | 4/6 — 67% |
| PROBE-C04 | Regulatory caveat omitted | 3/6 — 50% |
| PROBE-D05 | Soft rejection doubled down | 6/6 — 100% |
| PROBE-E01 | Thread leakage | 6/6 — 100% |
| PROBE-E02 | Generic peer names | 4/6 — 67% |
| PROBE-E03 | Opt-out channel ignored | 5/6 — 83% |
| PROBE-G03 | C-level escalation missed | 8/8 — 100% |

---

## How to Use

```python
from unsloth import FastLanguageModel
import torch

model, tokenizer = FastLanguageModel.from_pretrained(
    "bethelhem21/tenacious-judge-lora",
    max_seq_length=2048,
    load_in_4bit=True,
)
FastLanguageModel.for_inference(model)

SYSTEM_PROMPT = """You are a sales-outreach judge for Tenacious, a B2B sales agent.
Apply the 7-rule rubric in strict priority order:
1. SUPPRESS if any disqualifier is present (anti_offshore, local_only, do_not_contact)
2. SUPPRESS if prospect has opted out of the outreach channel
3. ESCALATE if recipient is C-level at a company with >2000 employees
4. BLOCK if output references content from a different thread
5. BLOCK if funding amount cited but funding_confidence is low
6. PENALISE if peer company names are generic or reused
7. PASS if none of the above apply
Respond with one of: SUPPRESS | ESCALATE | BLOCK | PENALISE | PASS
Then give a one-sentence rationale."""

context = {
    "company": "ExampleCo", "headcount": 50,
    "disqualifiers": ["anti_offshore"], "opt_out_channels": [],
    "funding_stage": "series_a", "funding_confidence": "high"
}
agent_output = "Hi, let me introduce our offshore engineering team..."

messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": f"Context:\n{context}\n\nAgent output:\n{agent_output}"},
]
inputs = tokenizer.apply_chat_template(
    messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
).to("cuda")

outputs = model.generate(inputs, max_new_tokens=64, temperature=0.0)
decision = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
print(decision)  # SUPPRESS\nProspect has anti_offshore disqualifier...
```

---

## Limitations

1. **Single-turn only.** The judge sees one context object + one agent output. It cannot
   evaluate failures that span a multi-turn conversation thread.

2. **C02 partial failure.** Bench-commitment probe accuracy is 67% (4/6). The context
   object lacks a structured `prior_commitments` field; the judge infers commitments
   from prose rationale, which is unreliable. Resolved in v0.2 with a schema change.

3. **C04 partial failure.** Regulatory-caveat probe accuracy is 50% (3/6). Regulated-industry
   examples were not in the training data. Do not deploy for finance/healthcare/defence
   prospects without retraining on a regulated-industry probe set.

4. **Signal lag.** Ground truth depends on CRM signals recorded at a point in time. A prospect
   who changed their stance after the signal was recorded will be incorrectly suppressed or
   sent to.

5. **200ms inference latency** (batch size 1, T4). Not suitable for real-time use cases.
   Designed for async pre-send queues.

---

## Kill-Switch Conditions

Remove this adapter and revert to the deterministic rule layer if:
- False-positive rate exceeds 15% over a rolling 500-prospect window
- Any probe drops below 50% accuracy on a weekly 20-decision spot-check
- Adapter fails to load or produces malformed output on >1% of calls
- A Tier-1 brand-damage event occurs that was not blocked, traced to a known probe

---

## Environmental Cost

| Phase | Cost |
|-------|------|
| Dataset generation | $0.00 (trace-derived + programmatic) |
| Multi-LLM synthesis | ~$1.50 (OpenRouter) |
| ORPO training | $0.00 (Colab T4 free tier, 17 min) |
| Inference per prospect | ~$0.00 (local adapter, no API fee) |
| **Total** | **< $1.50** |

---

## Citation

```bibtex
@misc{tenacious-judge-lora-2026,
  author = {Bethelhem Abay},
  title  = {Tenacious Judge LoRA: Preference-Tuned B2B Sales Outreach Judge},
  year   = {2026},
  url    = {https://huggingface.co/bethelhem21/tenacious-judge-lora}
}
```

**Training dataset:** Rafailov et al. (2023) DPO; Hong et al. (2024) ORPO;  
Gebru et al. (2021) Datasheets for Datasets.
