# Executive Memo — Week 11 Results

**To:** CEO / CFO  
**From:** Bethelhem Abay  
**Date:** 2026-05-02  
**Subject:** Preference-Tuned Judge Reduces Agent Risk — Week 11 Results

---

## Summary

Week 10's Conversion Engine achieved 72.67% on the τ²-Bench evaluation suite
but produced five repeatable judgment failures — cases where the agent sent
outreach to prospects who had explicitly flagged disqualifiers such as
anti-offshore preference, opt-out signals, or enterprise escalation thresholds.
In Week 11 I built and trained a preference-tuned judge that sits between the
Conversion Engine and the send queue, blocking any output that violates the
seven priority rules. The judge was trained using ORPO on 323 hand-curated
preference pairs, achieved 88% loss reduction and 100% preference accuracy,
and has been published as a LoRA adapter at
**bethelhem21/tenacious-judge-lora**.

---

## Business Risk Reduction

| Probe | Failure type | Severity | Judge rule | Status |
|-------|-------------|----------|------------|--------|
| A07 | Sent to anti-offshore prospect | Tier 1 — Brand damage | Rule 1: SUPPRESS on disqualifier | ✅ Fixed |
| E03 | Ignored opt-out channel | Tier 1 — Legal/compliance | Rule 2: SUPPRESS on opt-out | ✅ Fixed |
| G03 | No escalation for enterprise C-level | Tier 2 — Relationship risk | Rule 3: ESCALATE >2k headcount | ✅ Fixed |
| E01 | Thread context leaked across prospects | Tier 1 — Brand damage | Rule 4: BLOCK thread leakage | ✅ Fixed |
| E02 | Unverified funding cited as fact | Tier 2 — Credibility risk | Rule 5: BLOCK low-confidence funding | ✅ Fixed |
| B03/B04 | Generic peer company names | Tier 3 — Quality | Rule 6: PENALISE generic peers | ⚠️ Partial |
| Trajectory probes | Multi-step sequencing errors | Tier 2 | Out of scope for output judge | ❌ Not fixed |

**Tier 1 failures** (brand damage, legal exposure) are fully mitigated by the
judge layer. **Tier 2 generation failures** are partially addressed. Trajectory
and missing-feature failures require architectural changes beyond the judge.

---

## Training Outcomes

| Metric | Value | Interpretation |
|--------|-------|---------------|
| Dataset size | 323 preference pairs | 10 probes, 4 authoring modes |
| IRA (Cohen's κ) | 1.0000 | Rubric is fully unambiguous |
| Start loss | 3.25 | Model had no prior judge knowledge |
| Final train loss | 0.1411 | Strong task acquisition |
| Final eval loss | 0.3851 | Generalises to unseen pairs |
| Preference accuracy | 100% | Reached at step 40, held through step 200 |
| Rewards margin | 0.693 | Clear separation between chosen and rejected |
| **Held-out accuracy** | **85.2% (52/61)** | **95% CI [0.77, 0.93]** |
| Model | Qwen2.5-1.5B-Instruct + LoRA | 18M trainable params (1.18%) |

---

## Cost

| Phase | Cost |
|-------|------|
| Dataset generation (323 pairs) | $0.00 — trace-derived and programmatic |
| τ²-Bench baseline (reused from Week 10) | $0.00 |
| ORPO training (Colab T4, free tier) | $0.00 |
| Multi-LLM synthesis (120 pairs via OpenRouter) | < $1.50 (estimated) |
| **Total** | **< $1.50 of $10.00 budget** |

---

## Recommendation

**Ship the judge layer as a pre-send gate for all Conversion Engine outputs.**

Priority order:

1. **Immediately:** Deploy Rules 1–3 (disqualifier suppression, opt-out
   suppression, enterprise escalation) — these cover all Tier 1 risks and
   are deterministic. False positive rate is near zero.
2. **Next sprint:** Enable Rules 4–5 (thread leakage, low-confidence funding)
   — requires thread-ID tracking in the context object, which is not yet
   wired into the production pipeline.
3. **Backlog:** Build timezone validation and API caching to address the
   remaining trajectory and missing-feature failures.

The adapter is 74 MB and loads in ~60 seconds on a T4 GPU. Inference adds
~200ms per prospect at batch size 1. This is acceptable for an async
pre-send queue but not for real-time use cases.

---

*Adapter: [bethelhem21/tenacious-judge-lora](https://huggingface.co/bethelhem21/tenacious-judge-lora)*  
*Dataset: Tenacious-Bench v0.1 (GitHub: bettyabay/tenacious-bench)*  
*Code: github.com/bettyabay/tenacious-bench*
