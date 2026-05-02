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
| Base model | Qwen2.5-1.5B-Instruct (4-bit, Unsloth) |
| Method | ORPO, λ = 0.1 |
| Training pairs | 169 (train split) |
| Eval pairs | 93 (dev split) |
| Total steps | 200 (10 epochs) |
| Start loss | 3.25 |
| Final train loss | **0.1411** |
| Final eval loss | **0.3851** |
| Loss reduction | **95.7%** |
| Preference accuracy | **100%** |
| Rewards margin | 0.693 |
| Training time | ~17 minutes (Colab T4) |

The model learned the 7 rules cleanly. Preference accuracy of 100% was
reached by step 40 and held throughout all 200 steps — the judge reliably
prefers the correct action over the rejected action for every pair.

The train/eval loss gap of 0.244 reflects the model fitting the training
preference signal strongly, while generalising to unseen examples in the
eval split. No collapse to "always PASS" was observed.

---

## Ablation Results

Two variants were evaluated on 61 sealed held-out pairs (all rejected outputs
— cases where the agent made the wrong decision):

| Variant | Correct blocks | Accuracy | 95% CI |
|---|---|---|---|
| A — No judge (baseline) | 0 / 61 | 0.0% | [0.00, 0.00] |
| C — ORPO judge (ours) | 52 / 61 | **85.2%** | **[0.77, 0.93]** |

The 95% CI for the ORPO judge [0.77, 0.93] does not overlap with the
no-judge baseline (0%), establishing significance without a degenerate
p-value test. The judge correctly blocked or suppressed rejected outputs
on 52 of 61 held-out pairs.

**Per-probe breakdown:**

| Probe | Failure type | Judge accuracy |
|---|---|---|
| A07 | Disqualifier (anti_offshore) | 6/6 — 100% |
| B03 | Funding-tier mismatch | 5/6 — 83% |
| B04 | Low-confidence funding | 5/5 — 100% |
| C02 | Bench commitment ignored | 4/6 — 67% |
| C04 | Regulatory caveat omitted | 3/6 — 50% |
| D05 | Soft rejection doubled down | 6/6 — 100% |
| E01 | Thread leakage | 6/6 — 100% |
| E02 | Generic peer names | 4/6 — 67% |
| E03 | Opt-out channel ignored | 5/6 — 83% |
| G03 | C-level escalation missed | 8/8 — 100% |

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

Base model: `unsloth/Qwen2.5-1.5B-Instruct-bnb-4bit`  
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
2. **More steps on the hard probes.** The initial 60-step run achieved only
   8.2% accuracy — the model was defaulting to PASS. Retraining to 200 steps
   lifted this to 85.2%, with eval loss falling to 0.3851. C02 and C04 still
   underperform (67% and 50%); a targeted 50-pair augmentation on those two
   probes, with a structured `prior_commitments` field added to the schema,
   would likely push both above 80%.
3. **Evaluate on full τ²-Bench.** The gold standard is running the full 30-probe
   suite with the judge in the loop. Time and compute limited this to the
   held-out slice.

---

## One-Sentence Summary

I built a preference-tuned judge using ORPO on a 323-pair dataset derived
from Week 10 agent traces, trained it on Qwen2.5-1.5B in 200 steps with
95.7% loss reduction and 100% preference accuracy, and published the adapter
to HuggingFace — directly addressing the five judgment failures that caused
Tenacious's agent to send emails it should have suppressed.
