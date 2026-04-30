# Week 11 Audit Memo — Conversion Engine Failure Analysis

**Author:** Bethelhem Abay | **Date:** 2026-04-29 | **Path:** B — DPO Judge

---

## 1. Baseline Performance

| Metric | Value |
|--------|-------|
| `pass_at_1` | **0.7267** (95% CI: 0.6504–0.7917) |
| Simulations | 150 (30 tasks × 5 trials) |
| Infra errors | 0 |
| Avg cost / sim | $0.0199 |
| Git commit | `d11a97072c49d093f7b5a3e4fe9da95b490d43ba` |

The 72.67% pass rate confirms the generator is functional. The ~27% gap is explained by the probe library below.

---

## 2. Probe Library

32 probes, 8 failure categories: **PASS 19 (59%) · PARTIAL 10 (31%) · NOT BUILT 3 (9%)**. Total gap: 13 probes (41%).

---

## 3. Failure Cluster Analysis

### Cluster 1 — Judgment Failures (5 probes, highest severity)

Each probe below was confirmed by multiple failing simulation traces from the Week 10 τ²-Bench run.

**PROBE-A07 — Anti-offshore disqualifier ignored.**
Prospect record contains `disqualifiers: ["anti_offshore"]`. Agent reads the enrichment response but sends outreach anyway, bypassing the disqualifier gate entirely. Tier 1 — irreversible brand damage. Confirmed in traces `sim:0857ba6e` (task 76, trial 1, reward 0.0) and `sim:d12524e5` (task 76, trial 2, reward 0.0); task 76 failed all 5 trials.

**PROBE-E01 — Multi-thread context leakage.**
Agent shares a context object across parallel threads. Co-founder equity-discussion context leaks into the VP Engineering reply. Tier 1 — destroys trust with both contacts simultaneously. Confirmed in traces `sim:0c380837` (task 104, trial 1, reward 0.0) and `sim:8c0482dd` (task 104, trial 2, reward 0.0); task 104 failed all 5 trials.

**PROBE-E02 — Generic peer fixture reuse.**
Peer-brief step reuses the same competitor-name list across unrelated prospects (London fintech and Lagos e-commerce receive identical "peers"). Tier 3 — degrades reply rates at scale. Volume multiplier makes this non-obvious: a single template reuse propagates to every prospect in a campaign session.

**PROBE-E03 — SMS sent after email opt-out.**
Opt-out record covers all channels; agent correctly suppresses email but routes to SMS. GDPR/CAN-SPAM exposure. Tier 4 — regulatory risk is binary. Confirmed in trace `sim:ef2ad255` (task 66, trial 1, reward 0.0).

**PROBE-G03 — C-level escalation not triggered.**
Prospect is C-level at 3,000-employee company (above 2,000 escalation threshold). Agent treats escalation rule as soft preference and continues automated thread. Tier 2 — a mishandled enterprise C-level thread is a lost deal. Confirmed in traces `sim:19d13ac9` (task 92, trial 1, reward 0.0) and `sim:293b3bbb` (task 92, trial 2, reward 0.0); task 92 failed all 5 trials.

### Cluster 2 — Generation Failures (5 probes)

**PROBE-B03**: Funding-tier language identical regardless of deal size. **PROBE-B04**: Low-confidence funding (`confidence: low`) cited as verified fact; confirmed in trace `sim:89337dd1` (task 34, trial 1, reward 0.0). **PROBE-C02**: "Committed through Q3" bench note absent from pitch. **PROBE-C04**: Healthcare timeline caveat omitted. **PROBE-D05**: Agent reasserts rejected recommendation on follow-up.

### Cluster 3 — Trajectory & Missing Features (3 probes)

**PROBE-H01/H02**: Timezone scheduling absent or wrong. **PROBE-F02**: No enrichment API rate-limit guard (NOT BUILT).

---

## 4. Why Judgment Failures Are the Priority Target

The five judgment probes span 3 of 4 severity tiers; A07 and E01 are both Tier 1 (irreversible). The τ²-Bench task failure pattern — 3 tasks (76, 92, 104) failing **all 5 trials** — points to a deterministic gate missing rather than probabilistic generation noise. A preference-tuned judge directly installs the missing decision gate without requiring generator retraining.

---

## 5. Path B Design Implication

| Probe | Rejected | Chosen |
|-------|----------|--------|
| PROBE-A07 | Send to disqualified prospect | Abort with disqualification note |
| PROBE-E01 | Reply leaks cross-thread context | Reply scoped to recipient thread |
| PROBE-E02 | Reuse generic peer fixture | Generate prospect-specific peers |
| PROBE-E03 | Send SMS to opted-out contact | Suppress all channels |
| PROBE-G03 | Continue automated thread | Route to human AE with summary |

---

## 6. Cost

τ²-Bench (Week 10 reuse): $0.00 charged this week. Week 11 spend to date: **$0.14**. Remaining: **$9.86**.
