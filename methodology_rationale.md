# Methodology Rationale — Path B: Preference-Tuned ORPO Judge

**Author:** Bethelhem Abay · TRP1 Programme, Week 11  
**Date:** 2026-05-02  
**Path:** B — Preference-Tuned Judge (Odds-Ratio Preference Optimisation)

---

## 1. Why Path B, Not Path A or C

Week 10 τ²-Bench evaluation (150 simulations, 30 probes, 5 trials per probe) returned a
`pass_at_1` of **72.67%** (95% CI [0.65, 0.79]). Inspecting the 13 failing probes revealed
that **five failures were pure judgment failures** — cases where the Conversion Engine had
the correct signal in its context object and generated fluent text, but made the wrong
decision about whether to send, suppress, or escalate:

| Trace ID | Probe | Signal in context | Agent error |
|----------|-------|-------------------|-------------|
| `trace_A07_p003_r1` | PROBE-A07 | `disqualifiers: ["anti_offshore"]`, quote: *"I have had bad experiences with offshore teams"* | Sent pitch to anti-offshore founder |
| `trace_E03_p044_r3` | PROBE-E03 | `opt_out_channels: ["email"]` | Sent email to prospect who had opted out of email channel |
| `trace_G03_p078_r2` | PROBE-G03 | `headcount: 3800, recipient_role: "cto"` | Sent standard outreach instead of escalating to human account exec |
| `trace_E01_p012_r5` | PROBE-E01 | `thread_id: "thread_p_012_main"` | Output referenced conversation context from `thread_p_007_main` |
| `trace_B04_p021_r4` | PROBE-B04 | `funding_confidence: "low", funding_source: "unconfirmed press report"` | Cited `$20M Series A` as confirmed fact |

**Path A (SFT) was ruled out** because these are not generation failures — the agent can
write perfectly well. SFT teaches a model *what to write*, not *when not to write*. Fine-tuning
on correct traces would embed the judgment rules as a side effect of fitting to the output
distribution, producing a model that averages over thousands of normal `send` examples and
dilutes the five learned rules (Rafailov et al., 2023, §2 — this is the core motivation for
preference optimisation over SFT).

**Path C (PRM)** was considered but rejected: the five judgment failures are single-turn
errors — the agent reads a context object and acts. There are no multi-step reasoning
chains requiring step-level credit assignment. PRM annotation overhead (Source2Synth /
trajectory labelling) is not justified for single-turn suppression decisions.

**Path B (DPO-family) is correct** because:
1. Each judgment failure has a binary structure: a wrong action (rejected) and a correct
   action (chosen). This maps exactly to the DPO preference pair formulation.
2. The judge is being trained to assign higher log-probability to the correct action, not
   to generate new text. This is the task DPO and its variants were designed for.
3. ORPO (Hong et al., 2024) was selected over standard DPO specifically because it
   eliminates the reference model, saving ~3–4 GB VRAM on the Colab T4 free tier, and
   combines the SFT objective with the preference loss in a single pass — more stable
   on datasets below 500 pairs (Hong et al., 2024, Table 2).

---

## 2. Paper Foundations

**Rafailov et al. (2023) — DPO.** Preference optimisation without a separate reward model.
Establishes the theoretical equivalence with RLHF and the practical advantage of training
on (chosen, rejected) pairs. Applied here: the DPO loss provides the gradient signal that
makes the judge prefer the correct action over the wrong action. *Key equation used:*
`L_DPO = -E[log σ(β log(π_θ(y_w|x)/π_ref) - β log(π_θ(y_l|x)/π_ref))]`.

**Hong et al. (2024) — ORPO.** Odds-ratio preference optimisation. Removes the reference
model by replacing the KL penalty with an odds-ratio term computed from the policy itself.
Achieves comparable or better performance to DPO on preference datasets under 500 pairs.
Applied here: `ORPOConfig(beta=0.1)` with `Qwen2.5-1.5B-Instruct` as the backbone.

**Meng et al. (2024) — SimPO.** Simple preference optimisation with reference-free reward.
Reviewed as an alternative to ORPO; ORPO preferred because SimPO requires careful length
normalisation on short outputs (the judge responses are 2–4 tokens), which introduces
instability at batch size ≤ 8.

**Gebru et al. (2021) — Datasheets for Datasets.** Applied to Tenacious-Bench v0.1
dataset authoring: all seven sections completed in `publication/datasheet.md`.

---

## 3. Training Data Preparation

The training partition (169 pairs) was converted from `tenacious_bench_v0.1/train/pairs.jsonl`
to ORPO format using `pair_to_orpo()` in `training/colab_orpo_training.py`:

```python
{
  "prompt":   "<|im_start|>system\n[7-rule rubric]<|im_end|>\n<|im_start|>user\n[context + rejected output]<|im_end|>\n<|im_start|>assistant\n",
  "chosen":   "SUPPRESS\n[correct rationale]",
  "rejected": "PASS\n[wrong rationale]"
}
```

Output files: `training_data/train_orpo.jsonl` (169 pairs), `training_data/dev_orpo.jsonl`
(93 pairs). Contamination check run before sealing: 0 n-gram overlaps, 0 embedding
violations (cosine threshold 0.85), 0 pair-ID duplicates between training and held-out.

---

## 4. Training Configuration

| Hyperparameter | Value | Rationale |
|----------------|-------|-----------|
| Base model | `Qwen2.5-1.5B-Instruct` | Fits T4 VRAM in 4-bit; strong instruction following |
| LoRA rank (r) | 16 | Balance between capacity and overfitting on 169 pairs |
| lora_alpha | 16 | Scaling = alpha/r = 1.0 (neutral scaling) |
| lora_dropout | 0 | Unsloth recommendation for small datasets |
| ORPO lambda (β) | 0.1 | Default from Hong et al. (2024) |
| Epochs | 10 | 200 effective steps; loss fully plateaued by step 180 |
| Batch size (effective) | 8 | 2 per device × 4 gradient accumulation steps |
| Learning rate | 2e-4 | Standard for LoRA fine-tuning |
| Seed | 3407 | Matches `split_pairs.py` for full reproducibility |

Final held-out accuracy: **85.2%** (52/61 pairs, 95% CI [0.77, 0.93]).
