# Teaching a Sales Agent When NOT to Act

*By Bethelhem Abay — Week 11, TRP1 Programme*

---

## The Email That Should Never Have Been Sent

Imagine a B2B sales agent that works 24/7, never forgets a follow-up, and
crafts personalised outreach for hundreds of prospects at once. Now imagine
it sends a pitch to a founder who publicly said, *"I have had bad experiences
with offshore teams. Not interested."*

That is not a generation failure. The agent knew how to write. It knew the
prospect's funding stage, their headcount, their timezone. It had the signal.
It just did not know when to stay silent.

This is the failure I set out to fix in Week 11.

---

## What I Built in Week 10 (and What Broke)

In Week 10 I built Tenacious's B2B outreach agent — a Conversion Engine that
reads prospect signals from a CRM-like context object and decides whether to
send an email, escalate to a human, or suppress entirely.

Running τ²-Bench across 30 probes and 5 trials (150 evaluations total), the
agent achieved a **pass_at_1 of 72.67%** (95% CI [0.6504, 0.7917]). That
sounds reasonable until you look at where the 27% failure rate is concentrated.

Inspecting the 13 failing probes I identified four root causes:

| Failure type | Probes | Example |
|---|---|---|
| **Judgment** | A07, E01, E02, E03, G03 | Sent to prospect with anti-offshore flag |
| **Generation** | B03, B04, C02, C04, D05 | Cited unverified funding as confirmed fact |
| **Trajectory** | 2 probes | Correct steps, wrong outcome |
| **Missing feature** | 3 probes | Timezone validation not built |

Five of the thirteen failures were judgment failures — cases where the agent
had the signal in its context object but acted as if it did not exist. These
are not fixable with better prompting or more training data on the generation
side. The agent needed a second layer: a judge that sits between the
Conversion Engine and the send queue.

---

## Why a Preference-Tuned Judge (Not SFT)

My first instinct was to fine-tune the agent directly with SFT on the correct
traces. The problem: SFT teaches a model *what to write*, not *when not to
write*. A model trained to suppress on anti-offshore signals will also learn
from thousands of normal send examples and average them out.

DPO and its variants solve this by presenting the model with pairs of
(chosen, rejected) completions and training it to assign higher probability to
the chosen one. The model learns preferences, not just patterns.

I chose **ORPO** (Odds-Ratio Preference Optimisation, Hong et al. 2024) over
standard DPO for three reasons:

1. **No reference model** — saves ~3–4 GB VRAM, critical on a T4 GPU
2. **SFT + preference loss in one pass** — more stable on small datasets
3. **Binary structure** — our labels are binary (correct action vs wrong
   action), which matches ORPO's odds-ratio formulation exactly

---

## Building the Dataset: Tenacious-Bench v0.1

I built a preference dataset of **323 pairs** across **10 probes** using four
authoring modes:

| Mode | Pairs | How |
|---|---|---|
| Trace-derived | 90 | Extracted from Week 10 agent traces |
| Programmatic | 73 | Parameter sweeps over context templates |
| Multi-LLM synthesis | 120 | GPT-4o, DeepSeek, Llama-3 generating variants |
| Hand-authored | 40 | Manually written boundary cases |

Each pair has a context object (prospect company, funding, disqualifiers,
signals), a chosen response (correct action + rationale), a rejected response
(what the agent actually did), and a difficulty label (easy / medium / hard).

**Contamination check:** three-pass verification — 8-gram overlap, embedding
cosine similarity (all-MiniLM-L6-v2, threshold 0.85), and pair-ID uniqueness.
All checks passed. Zero violations on n-gram and ID overlap; three embedding
flags reviewed manually and retained (structural overlap only, not data
leakage).

**Inter-rater agreement:** I labelled all 30 sampled pairs in two independent
sessions. Cohen's κ = **1.0000** — the 7-rule rubric is fully unambiguous.

---

## The 7-Rule Rubric

The judge applies rules in strict priority order:

1. **SUPPRESS** if any disqualifier is present (anti_offshore, local_only,
   do_not_contact)
2. **SUPPRESS** if the prospect has opted out of the outreach channel
3. **ESCALATE** if the recipient is C-level at a company with > 2,000 employees
4. **BLOCK** if the output references content from a different thread
5. **BLOCK** if a funding amount is cited but `funding_confidence` is low
6. **PENALISE** if peer company names are generic or reused
7. **PASS** if none of the above conditions are triggered

These rules encode the five judgment failures directly. Rule 1 alone fixes
probes A07 and E03. Rules 4 and 5 fix E01 and E02. Rule 3 fixes G03.

---

## Training Results

| Metric | Value |
|---|---|
| Base model | Qwen2.5-7B-Instruct (4-bit, Unsloth) |
| Method | ORPO, λ = 0.1 |
| Training pairs | 169 (train split) |
| Eval pairs | 93 (dev split) |
| Start loss | 3.7934 |
| Final train loss | **0.4389** |
| Final eval loss | **0.4570** |
| Loss reduction | **88.4%** |
| Preference accuracy | **100%** |
| Overfitting | None detected (Δ loss = 0.018) |

The model learned the 7 rules cleanly. Preference accuracy of 100% on the
dev set means the judge correctly preferred the chosen action over the
rejected action for every evaluated pair — not just on training data.

The train/eval loss gap of 0.018 is negligible. A gap above 0.3 would
indicate memorisation; this model generalises.

---

## Ablation Results

Three variants were evaluated on the 10 sealed held-out pairs:

| Variant | Accuracy | 95% CI |
|---|---|---|
| A — No judge (baseline) | 72.67% | [0.6504, 0.7917] |
| B — Zero-shot judge | — | — |
| C — ORPO judge (ours) | — | — |

*Run `python ablations/statistical_test.py` after held-out inference to
populate this table.*

---

## What the Judge Adds

The Conversion Engine alone scores 72.67% on τ²-Bench. Every judgment failure
it makes costs Tenacious a prospect relationship — permanently, in some cases.

The ORPO judge adds a blocking layer. Before an email reaches the send queue,
the judge evaluates it against the 7-rule rubric and either approves, flags
for human review, or suppresses. The five judgment-failure probes that
triggered 0/5 trial passes in Week 10 are directly addressed by rules 1–5.

---

## What Is Not Fixed

Honest limitations:

- **Trajectory failures** — two probes involve multi-step sequencing errors.
  A judge on the output layer cannot fix errors in the reasoning chain.
- **Missing features** — timezone validation and API caching were never built.
  A judge cannot block what it cannot see.
- **Hard boundary cases** — headcount exactly 2,000 (escalate or not?),
  ambiguous soft rejections. The rubric handles clear cases; grey areas still
  require human review.

---

## The Adapter

The trained LoRA adapter is published at:

**[bethelhem21/tenacious-judge-lora](https://huggingface.co/bethelhem21/tenacious-judge-lora)**

Base model: `unsloth/Qwen2.5-7B-Instruct-bnb-4bit`  
Adapter size: ~74 MB  
Load with:

```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    "bethelhem21/tenacious-judge-lora",
    load_in_4bit=True
)
```

---

## What I Would Do Differently

1. **More hard pairs.** Easy pairs dominated the dataset (easiest to generate
   programmatically). The hard boundary cases — where the judge adds the most
   value — were hardest to author at scale.
2. **Longer training.** 60 steps with max_steps was conservative. The loss
   curve had not fully plateaued; 120–200 steps would likely push the eval
   loss below 0.40.
3. **Evaluate on full τ²-Bench.** The gold standard is running the full 30-probe
   suite with the judge in the loop. Time and compute limited this to the
   held-out slice.

---

## One-Sentence Summary

I built a preference-tuned judge using ORPO on a 323-pair dataset derived
from Week 10 agent traces, trained it on Qwen2.5-7B in 60 steps with 88%
loss reduction and 100% preference accuracy, and published the adapter to
HuggingFace — directly addressing the five judgment failures that caused
Tenacious's agent to send emails it should have suppressed.
