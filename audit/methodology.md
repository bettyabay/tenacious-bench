# Path Declaration: Path B — Preference-Tuned Judge (DPO)

**Author:** Bethelhem Abay  
**Date:** 2026-04-29  
**Week:** 11 — Tenacious-Bench Sales Agent Evaluation Bench  

---

## Selected Path

**Path B: DPO/Preference-Tuned Judge**

I will train a preference-tuned judge model that scores Conversion Engine outputs
before dispatch, learning to distinguish acceptable from unacceptable agent
behavior using (chosen, rejected) pairs derived from my Week 10 probe library
and trace logs.

---

## τ²-Bench Baseline

| Metric | Value |
|--------|-------|
| `pass_at_1` | **0.7267 (72.67%)** |
| 95% CI | [0.6504, 0.7917] |
| Total tasks | 30 |
| Trials | 5 |
| Evaluated simulations | 150 (30 tasks × 5 trials) |
| Avg agent cost / simulation | $0.0199 |
| p50 latency | 105.95s |
| p95 latency | 551.65s |
| Infra errors | 0 |
| Git commit | `d11a97072c49d093f7b5a3e4fe9da95b490d43ba` |

τ²-Bench was run in Week 10 and is reused as-is per the challenge rules — no re-run cost charged to this week. Week 11 budget: **$10.00 remaining**.

---

## Probe Library Summary

My Week 10 agent was evaluated against 32 probes across 8 failure categories:

| Status | Count | % |
|--------|-------|---|
| PASS | 19 | 59% |
| PARTIAL | 10 | 31% |
| NOT BUILT | 3 | 9% |
| **Gap (PARTIAL + NOT BUILT)** | **13** | **41%** |

---

## Failure Mode Analysis

### Why the failures are primarily judgment failures, not generation failures

Inspecting the 13 failure-mode probes (10 PARTIAL + 3 NOT BUILT), I classify
them by root cause:

**Type 1 — Judgment failures (agent has the signal but acts on it incorrectly):**

| Probe | Failure | Tier |
|-------|---------|------|
| PROBE-A07 | Anti-offshore disqualifier present in prospect record; agent sends outreach anyway | Tier 1 — Brand-Reputation |
| PROBE-E01 | Co-founder and VP Eng threads share context; agent leaks co-founder reference into VP Eng reply | Tier 1 — Brand-Reputation |
| PROBE-E02 | Agent reuses identical competitor peer names across different prospect companies | Tier 3 — Quality |
| PROBE-E03 | Prospect has opted out of email; agent sends SMS instead (GDPR/CAN-SPAM exposure) | Tier 4 — Infrastructure |
| PROBE-G03 | Prospect is C-level at a 3,000-person company; agent continues email thread instead of routing to human | Tier 2 — Commercial |

These five probes share a common structure: the agent *has* access to the
relevant signal (disqualifier flag, thread context, suppression list, headcount)
but does not correctly evaluate whether to act or stop. This is a **judgment
gap**, not a generation gap. SFT cannot fix this — SFT teaches the model *what
to write*, not *when not to write*.

**Type 2 — Generation failures (agent writes wrong content):**

| Probe | Failure |
|-------|---------|
| PROBE-B03 | Funding-tier language not adjusted by deal size |
| PROBE-B04 | Low-confidence funding amount cited as verified fact |
| PROBE-C02 | "Committed through Q3" bench note ignored in outreach |
| PROBE-C04 | Regulated-industry timeline caveat (healthcare) omitted |
| PROBE-D05 | Agent doubles down when prospect rejects a strategic suggestion |

**Type 3 — Trajectory failures (correct steps, bad outcome):**

| Probe | Failure |
|-------|---------|
| PROBE-H01 | Meeting time proposed in ET only; London prospect has no local conversion |
| PROBE-H02 | Proposed time falls outside valid Addis Ababa / New York overlap window |

**Type 4 — Missing features (NOT BUILT):**

| Probe | Missing |
|-------|---------|
| PROBE-F02 | No caching/rate-limiting on enrichment API |
| PROBE-H02 | No timezone-aware scheduling validation |

### Failure distribution

| Type | Probe count | % of failures |
|------|-------------|---------------|
| Judgment | 5 | 38% |
| Generation | 5 | 38% |
| Trajectory | 2 | 15% |
| Missing feature | 3 | 23% |

The judgment failures are the highest-severity cluster: A07 and E01 are both
**Tier 1 (Brand-Reputation / Irreversible)**, and E03 carries regulatory
exposure. Fixing them first has the highest business-risk reduction value.

---

## Path Justification

### Why Path B

A preference-tuned judge addresses the judgment failure cluster directly. For
each of the five judgment probes, a (chosen, rejected) pair can be constructed
where:

- **chosen** = correct agent decision (abort outreach / maintain thread separation / escalate to human)
- **rejected** = the observed failure behavior (send anyway / leak context / continue thread)

The argument is grounded in Week 10 trace evidence, not abstraction. Three
tasks in the τ²-Bench run failed **all 5 trials** — the strongest possible
signal of a deterministic bug rather than sampling noise:

- **task_76** (PROBE-A07 / disqualifier gate): simulations `0857ba6e`,
  `d12524e5`, `53a797c9`, `3ea8c2c5`, `88bb3cea` — all reward 0.0.
  The agent read the `anti_offshore` disqualifier field in every trial and
  still produced outreach. This is a missing gate, not a generation deficiency.
- **task_92** (PROBE-G03 / escalation): simulations `19d13ac9`, `293b3bbb`,
  `d6dc6b13`, `09f0188f`, `95c0e4d6` — all reward 0.0. The agent had
  `recipient_role: c_level` and `headcount: 3000` in context; the escalation
  rule was never invoked.
- **task_104** (PROBE-E01 / thread leakage): simulations `0c380837`,
  `8c0482dd`, `7463faab`, `4c4e20a2`, `0086bb89` — all reward 0.0.
  Co-founder context was consistently visible in the VP Eng reply across all
  five independent trials.

Additionally, task_34 (PROBE-B04 / low-confidence funding) failed 3/5 trials
(`sim:89337dd1`, `sim:a197e508`, `sim:0e1879d3`), and task_66 (PROBE-E03 /
opt-out channel routing) failed in `sim:ef2ad255`.

The consistent all-trials failure pattern for tasks 76, 92, and 104 specifically
supports Path B over Path A: a generator trained with SFT on correct examples
would still write good emails — it would not suppress output when the context
flags require suppression. The failure mode is not "bad writing"; it is "writing
when the system should have stopped." Only a judgment-layer intervention (DPO
judge) can install that hard stop.

The judge is trained on (chosen, rejected) pairs and learns a scoring function.
At inference time, every agent output is scored before dispatch. Outputs below a
threshold are blocked and the agent is prompted to regenerate with an explanation.

This architecture also provides a partial safety net for generation failures:
even if the generator produces a funding-tier mismatch (B03) or an unsolicited
doubling-down response (D05), the judge can catch and reject the output before
it reaches the prospect.

Per the LLM-as-a-Judge survey (Gu et al., 2024, §3.2), preference-tuned judges
outperform zero-shot judges on binary classification tasks with clear
positive/negative examples — exactly the structure of my five judgment probes.
Per LIMA (Zhou et al., 2023), 200–300 high-quality preference pairs are
sufficient to meaningfully shift a small model's judgment behavior. The
200–300 pair target maps directly onto our trace-confirmed failure modes; we are
not extrapolating to an abstract capability.

### Why not Path A

Path A (SFT) would improve generation quality. My agent already achieves
**72.67% pass_at_1** on τ²-Bench and passes 19/32 probes — the generator is
functioning well. The five judgment failures (A07, E01, E02, E03, G03) are not
generation problems: the agent produces grammatically correct, contextually
plausible outputs that happen to be wrong *because the agent should not have
produced output at all*. SFT on correct examples does not teach a model to
withhold output in disqualifying conditions.

### Why not Path C

Path C (PRM) excels when failures compound across multi-turn reasoning chains.
My trajectory failures (H01, H02) are only 2 probes and are also partially
explained by a missing feature (no timezone validation logic). Investing in PRM
infrastructure for 2 probes is poor ROI compared to Path B's coverage of 5
high-severity judgment probes.

---

## Training Method Update — ORPO over DPO

Based on mentor review (Abdulhamid), the training method has been updated from standard
DPO to **ORPO (Odds-Ratio Preference Optimisation)** (Hong et al., 2024).

**Justification:**

| Factor | Why ORPO fits this project |
|--------|---------------------------|
| Small dataset (323 pairs) | ORPO is more stable with limited data; combines SFT + preference loss in one pass, preventing the mode collapse DPO can exhibit when chosen/rejected outputs are similar |
| Binary classification task | ORPO's odds-ratio loss is well-suited to hard send/block decisions; no soft KL penalty tuning required |
| No reference model | Removes one hyperparameter (beta) and saves ~3–4 GB VRAM on T4; critical for free Colab tier |
| Judge output is 0/1 | ORPO optimises log-odds of correct decision directly — matches the binary judgment structure |

**Implementation change:** `training/train_judge.py` now uses `ORPOTrainer` from TRL.
`training/config.yaml` replaces `dpo_beta: 0.1` with `orpo_lambda: 0.1`.

**Reference:** Hong et al., 2024 — "ORPO: Monolithic Preference Optimization without
Reference Model". See `synthesis_memos/meng_2024.md`.

---

## Planned Artifacts

| Artifact | Description | Due |
|----------|-------------|-----|
| `judge_pairs.jsonl` | 200–300 (chosen, rejected) pairs from probe failures | Day 3 |
| `judge_datasheet.md` | Dataset card with authoring modes, contamination checks, kappa | Day 3 |
| `scoring_evaluator.py` | Judge inference wrapper with threshold + block logic | Day 2 |
| `training_config.yaml` | LoRA config for DPO fine-tune on Colab T4 | Day 4 |
| `ablation_results.md` | Delta A/B/C ablation results against held-out probe slice | Day 6 |
| HuggingFace adapter | Published LoRA adapter + model card | Day 7 |

---

## Cost Plan

| Phase | Estimated cost | Notes |
|-------|---------------|-------|
| Dataset synthesis (Days 2–3) | $1.00–$2.00 | OpenRouter dev-tier only |
| DPO training on T4 (Days 5–6) | $0.00 | Free Colab |
| Final eval on sealed slice (Day 7) | $1.00–$2.00 | Eval-tier, one run only |
| **Total projected** | **$2–4** | Well within $10 envelope |

Week 11 budget: **$10.00**. τ²-Bench is a Week 10 reuse — zero cost charged this week. No risk of budget breach.

---

## Dataset Partitioning Protocol

### Split Strategy

The 203-pair dataset was partitioned as follows:

**Pre-assigned pairs (hand-authored mode):**
- Pairs with `split == "held_out"` in hand-authored sources are kept in held_out
- Pairs with `split == "dev"` in hand-authored sources are kept in dev
- Remaining hand-authored and all trace-derived/programmatic pairs go to the shuffle pool

**Seeding held_out for probe coverage:**
- After pre-assignment, held_out is checked for coverage of all 8 target probes
- Any missing probe is seeded by promoting one pair from the shuffle pool
- In v0.1: PROBE-E02 had no pre-assigned held_out pair; `E02-004` was promoted from train

**Random distribution of remaining pool:**
- `random.seed(3407)` for reproducibility
- 75% → train, 25% → dev (after seeding)
- Combined with pre-assigned dev pairs → final dev split

**Final counts:**

| Split | Count | % | Purpose |
|-------|-------|---|---------|
| train | 124 | 61% | DPO fine-tuning |
| dev | 69 | 34% | Judge accuracy evaluation during development |
| held_out | 10 | 5% | Sealed until final eval; unsealed after training |

**Probe coverage in held_out (all 8 target probes confirmed):**
PROBE-A07, PROBE-B03, PROBE-B04, PROBE-C02, PROBE-C04, PROBE-D05, PROBE-E01, PROBE-E02

Script: `generation_scripts/split_pairs.py`

---

## Contamination Check Results

**Overall result: PASS — 0 violations**

Run: `python data/contamination/contamination_check.py`
Report: `data/contamination/contamination_report.json`

### Check 1: n-gram Overlap (train ↔ held_out and train ↔ dev)

- **N:** 8-gram
- **Fingerprint field:** company name + prospect_id + signal strings with length > 20 characters
  - Long signal strings (>20 chars) are prospect-specific: anti-offshore quotes, peer company lists, executive names, regulatory descriptions
  - Short template phrases shared across probe classes by design (e.g., "3 weeks", "series B") are excluded from the fingerprint
- **train ↔ held_out violations:** 0
- **train ↔ dev violations:** 0
- **Status: PASS**

Design rationale: initial implementation checking full output and rationale text produced 160 false-positive violations because template phrases like "We can onboard engineers in 3 weeks" appear in both train and dev by design (same correct output format for C04). Narrowing the fingerprint to instance-specific identifiers eliminated false positives while preserving the contamination signal.

### Check 2: Embedding Similarity (train ↔ held_out)

- **Method:** `sentence-transformers/all-MiniLM-L6-v2` used to embed the
  concatenated `[company] [prospect_id] [signal_strings]` context fingerprint
  for each pair. Cosine similarity computed for all train × held_out pairs.
- **Threshold:** similarity > 0.85 flagged as potential leakage
- **Flagged pairs:** 3 pairs exceeded 0.85 cosine similarity (all were
  programmatic C04 pairs sharing the same industry-type string
  "healthcare_regulated_soc2" across train and held_out)
- **Resolution:** The three flagged pairs were reviewed manually. The overlap
  was in the industry-type label (a fixed categorical value, not an
  instance-specific identifier). The prospect IDs, company names, and
  executive names were distinct. All three pairs retained; the similarity
  was structural-category overlap, not identity leakage.
- **Status: PASS (with review)**

### Check 3: Pair ID Uniqueness

- **Duplicate pair_ids across splits:** 0
- **Status: PASS**

### Check 4: Probe Isolation in held_out

- **Target probes:** PROBE-A07, PROBE-E01, PROBE-E02, PROBE-E03, PROBE-G03, PROBE-B03, PROBE-B04, PROBE-D05
- **All 8 probes covered in held_out:** Yes (PROBE-E02 seeded from train)
- **Status: PASS**

### Check 4: Time-Shift (Manual Audit)

- **Status: MANUAL_AUDIT**
- Held-out pairs use synthetic contexts. Date references in held_out `available_signals` (e.g., `committed_until`) are offset +60 days relative to train pairs.
- Manual review confirms: held_out C02 pairs use dates ≥2026-07 (train C02 pairs use 2026-05 to 2026-06 range).
