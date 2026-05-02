# Intra-Rater Agreement Report

**Dataset:** tenacious_bench_v0.1
**Date:** 2026-05-02
**Annotator:** Bethelhem Abay (human)
**Method:** Intra-rater — same annotator, two independent labeling sessions
**Target:** Cohen's κ ≥ 0.80

---

## Protocol

| Item | Value |
|------|-------|
| Sample size | 30 pairs |
| Sampling | 3 per probe × 10 probes, stratified by difficulty (≥1 easy, ≥1 medium, ≥1 hard) |
| Seed | 42 |
| Session 1 | 2026-04-29 |
| Session 2 | 2026-04-30 |
| Label definition | 1 = chosen response is correct, 0 = chosen response is wrong, ? = skip |

**Script:** `generation_scripts/run_ira.py`  
**Sample file:** `generation_scripts/ira_sample.jsonl`  
**Labels:** `generation_scripts/ira_labels_session1.txt`, `generation_scripts/ira_labels_session2.txt`

---

## Results

| Metric | Value |
|--------|-------|
| Pairs compared | 30 |
| Agreements | 30 |
| Disagreements | 0 |
| Raw agreement | 100.0% |
| Cohen's κ | 1.0000 |
| Threshold (κ ≥ 0.80) | ✓ PASS |

---

## Disagreement Analysis

*(Populated after running `python generation_scripts/compute_kappa.py`)*

Disagreement categories tracked:

| Category | Example probe | Expected issue |
|----------|--------------|----------------|
| Boundary conditions | G03 | headcount=2000 (no escalate) vs 2001 (escalate) |
| Soft signals | D05 | soft rejection ("Not a priority") vs strong rejection |
| Compound rules | A07 + E03 | which rule fires first |
| Generic vs specific peers | E02 | judgment on specificity threshold |
| Thread leak severity | E01 | low-severity leaks (short references) |

---

## Conclusion

κ = 1.0000 (100% raw agreement, 0 disagreements across 30 pairs). The rubric is fully consistent — all 7 rules produced unambiguous labels in both sessions. No rubric revision required. Dataset is cleared for ORPO training.

---

## Kappa Reference

| κ range | Interpretation |
|---------|---------------|
| < 0.60 | Poor — revise rationale fields |
| 0.60–0.70 | Moderate — acceptable with caveats |
| 0.70–0.80 | Substantial — close to target |
| ≥ 0.80 | Target — proceed to ORPO training |
| ≥ 0.90 | Near-perfect — note in model card |
