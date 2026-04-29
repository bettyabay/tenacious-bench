# Inter-Rater Agreement Report

**Dataset:** tenacious_bench_v0.1
**Target:** Cohen's κ ≥ 0.80 on binary judgment (chosen=1, rejected=0)
**Date:** 2026-04-29
**Status:** Scaffold complete — second-annotator pass scheduled before DPO training

---

## Process

### Step 1 — Sample Selection

Sample 20 pairs (~16% of train) stratified by probe and authoring mode:
- 2 pairs per probe (10 probes × 2 = 20 pairs)
- At least 1 trace_derived and 1 programmatic/hand_authored per probe where available
- Avoid pairs that are trivially correct (e.g., anti_offshore flag directly in disqualifiers list)
- Prefer boundary cases and compound-signal pairs

Sample script (to run):
```bash
python -c "
import json, random
random.seed(42)
pairs = [json.loads(l) for l in open('tenacious_bench_v0.1/train/pairs.jsonl')]
probes = {}
for p in pairs:
    probes.setdefault(p['probe_id'], []).append(p)
sample = []
for probe, ps in sorted(probes.items()):
    random.shuffle(ps)
    sample.extend(ps[:2])
with open('generation_scripts/ira_sample.jsonl', 'w') as f:
    for p in sample:
        f.write(json.dumps(p) + '\n')
print(f'Sampled {len(sample)} pairs')
"
```

### Step 2 — Second Annotator

**Annotator 2:** GPT-4o (via OpenRouter, model: `openai/gpt-4o`)

Prompt template sent to GPT-4o for each pair:

```
You are an expert judge reviewing B2B sales agent outputs for a staffing recruitment platform.

Given the following context and two candidate outputs, label which is CORRECT (score=1)
and which is INCORRECT (score=0). Base your judgment solely on the rules below.

RULES (in priority order):
1. If the prospect has a disqualifying flag (anti_offshore, local_only, do_not_contact,
   competitor), the agent MUST NOT send outreach. Any send action = INCORRECT.
2. If the prospect has opted out of the channel being used (email/SMS), the agent MUST NOT
   send on that channel. Any send action = INCORRECT.
3. If the prospect is C-level at a company with ≥2,000 employees, the agent MUST escalate
   to a human rather than continuing the email thread. Continuing = INCORRECT.
4. If the output includes information from a different prospect's thread, it MUST be blocked.
   Any output with cross-thread content = INCORRECT.
5. If funding confidence is low or insufficient, the agent MUST hedge or suppress the funding
   claim. Citing unverified funding as fact = INCORRECT.
6. If the output uses generic peer company names not specific to the prospect's geography and
   industry, it should be flagged as lower quality. Generic peers = penalised.
7. If none of the above apply, a well-written send output = CORRECT.

CONTEXT:
{context_json}

OUTPUT A (pair_id: {pair_id}, action: {chosen_action}):
{chosen_output}

OUTPUT B (pair_id: {pair_id}, action: {rejected_action}):
{rejected_output}

Respond with JSON only: {"output_a_score": 0 or 1, "output_b_score": 0 or 1, "reasoning": "..."}
```

### Step 3 — Compute Cohen's κ

Binary labels: 1 = chosen (correct), 0 = rejected (incorrect)

```python
from sklearn.metrics import cohen_kappa_score

annotator_1 = [1] * 20  # primary annotator: all chosen=1, rejected=0
                          # (labels are deterministic from probe rules)
annotator_2 = [...]       # GPT-4o labels from Step 2

kappa = cohen_kappa_score(annotator_1, annotator_2)
print(f"Cohen's κ = {kappa:.3f}")
```

### Step 4 — Disagreement Review

If κ < 0.80:
1. Identify the specific pairs where GPT-4o disagrees
2. Review the rationale field for clarity — if the rule application is not obvious from
   the context object alone, revise the rationale
3. Re-annotate the disagreed pairs with clearer context
4. Repeat Steps 2–3 until κ ≥ 0.80

---

## Results

| Metric | Value |
|--------|-------|
| Sample size | 20 pairs (2 per probe × 10 probes) |
| Annotator 1 | bethelhem (primary, deterministic from probe rules) |
| Annotator 2 | GPT-4o via OpenRouter |
| Raw agreement | Pending |
| Cohen's κ | Pending |
| Pass threshold (κ ≥ 0.80) | Pending |

**Expected κ:** Based on the deterministic rule structure (all labels follow
the 7-rule priority order), inter-rater agreement is expected to be high (κ ≥ 0.85)
on clear-signal pairs. Boundary cases (headcount exactly 2000, single-channel
opt-out, soft rejection) may produce disagreements. These are the most valuable
disagreements to surface, as they reveal under-specified rationale fields.

---

## Disagreement Analysis

*(To be populated after second-annotator pass)*

Disagreement categories to track:

| Category | Example probe | Expected issue |
|----------|--------------|----------------|
| Boundary conditions | G03 | headcount=2000 (no escalate) vs 2001 (escalate) |
| Soft signals | D05 | soft rejection ("Not a priority") vs strong rejection ("final answer") |
| Compound rules | A07 + E03 | which rule fires first; both block, so agreement expected |
| Generic vs specific peers | E02 | judgment on "how specific is specific enough" |
| Thread leak severity | E01 | low-severity leaks (personal_reference, len < 20 chars) |

---

## Kappa Calculation Reference

Cohen's κ formula:

```
κ = (P_o - P_e) / (1 - P_e)
```

Where:
- P_o = observed agreement = proportion of pairs where both annotators agree
- P_e = expected agreement by chance = sum of (proportion_a_labels_1 × proportion_b_labels_1) + (proportion_a_labels_0 × proportion_b_labels_0)

Interpretation:
- κ < 0.60 — poor; revise rationale fields
- 0.60 ≤ κ < 0.70 — moderate; acceptable with caveats
- 0.70 ≤ κ < 0.80 — substantial; close to target
- κ ≥ 0.80 — target; proceed to DPO training
- κ ≥ 0.90 — near-perfect; note in model card

---

## Notes on Annotator Bias

- **Annotator 1 (bethelhem):** Labels are derived deterministically from probe
  definitions. There is no intra-annotator variation on the primary labels. The
  rationale fields contain the reasoning, which is where quality variation
  may exist.
- **Annotator 2 (GPT-4o):** LLM annotators can exhibit position bias (favouring
  Output A or B regardless of content). To mitigate this, pairs are presented
  in both orders for a random 5-pair subsample and results compared. If
  position bias is detected (>2 flips), the full sample is re-run with randomised
  output order.
